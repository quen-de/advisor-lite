import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Coroutine
from dataclasses import dataclass, field

import asyncpg
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)

from advisor.agents import ADVISOR_SPEC_PATH, CAPABILITY_TYPES
from advisor.agents.capabilities.core import AdvisorDeps, CitationRepo
from advisor.config import Settings, resolve_model
from advisor.service import chats, portfolio_store

logger = logging.getLogger(__name__)

ERROR_MESSAGE = 'The agent failed to answer. Try again.'

# Text a model streams before its tool calls is commentary, not answer, but
# which one it is only becomes knowable once a tool call follows. Holding the
# first characters of every text part back this long settles most cases
# quietly: commentary is short and a tool call confirms it while it is still
# buffered, while a real answer overflows the holdback within a second.
TEXT_HOLDBACK = 300

TITLE_INSTRUCTIONS = (
    'Title a conversation that opens with the given message. '
    'Three to six words, plain text, no quotes, no trailing punctuation.'
)


def status_text(part: ToolCallPart) -> str:
    """Human-readable progress line for a tool call."""
    if part.tool_name == 'get_portfolio':
        return 'Reading the portfolio'
    if part.tool_name == 'web_search':
        query = part.args_as_dict().get('query')
        return f'Searching the web for "{query}"' if query else 'Searching the web'
    if part.tool_name == 'get_page':
        url = part.args_as_dict().get('url')
        return f'Reading {url}' if url else 'Reading a page'
    return f'Running {part.tool_name}'


@dataclass
class ChatService:
    pool: asyncpg.Pool
    settings: Settings
    _background: set[asyncio.Task] = field(default_factory=set, init=False, repr=False)

    async def stream_reply(self, chat_id: str, user_text: str) -> AsyncGenerator[dict]:
        """Run the agent on one user message.

        Yields status events as tools run and delta events while the answer
        streams, then sources (with the processed text) and done. A first
        message also starts the titling task immediately, so its title event
        is yielded as soon as the task finishes - between other events when
        the title beats the answer, after done otherwise. The task outlives
        a client disconnect. On failure yields a single error event and
        persists nothing.
        """
        title_task: asyncio.Task[str | None] | None = None
        try:
            agent = Agent.from_file(
                ADVISOR_SPEC_PATH,
                deps_type=AdvisorDeps,
                custom_capability_types=CAPABILITY_TYPES,
                model=resolve_model(self.settings, test_call_tools=['get_portfolio']),
            )
            portfolio = await portfolio_store.get_portfolio(self.pool)
            if portfolio is None:
                raise RuntimeError('portfolio not seeded')
            known = await chats.get_citations(self.pool, chat_id)
            deps = AdvisorDeps(portfolio=portfolio, citations=CitationRepo(known))
            history = await chats.get_model_history(self.pool, chat_id)
            if not history:
                title_task = self._spawn(self._title_chat(chat_id, user_text))
            async with agent.iter(user_text, deps=deps, message_history=history or None) as run:
                async for event in self._run_events(run):
                    yield event
                    if title_task is not None and title_task.done():
                        title = title_task.result()
                        title_task = None
                        if title:
                            yield {'type': 'title', 'chat_id': chat_id, 'title': title}
                result = run.result
                assert result is not None
            # The citations capability's output hook already stripped orphan
            # markers from result.output and filled deps.citations.referenced.
            text, sources = result.output, deps.citations.referenced
            new_messages_json = ModelMessagesTypeAdapter.dump_json(result.new_messages())
            await chats.append_exchange(
                self.pool,
                chat_id,
                user_text,
                text,
                sources,
                new_messages_json,
                citation_state=deps.citations.sources(),
            )
            yield {'type': 'sources', 'sources': sources, 'text': text}
            yield {'type': 'done', 'chat_id': chat_id}
            if title_task is not None:
                title = await asyncio.shield(title_task)
                if title:
                    yield {'type': 'title', 'chat_id': chat_id, 'title': title}
        except Exception:
            logger.exception('chat run failed')
            if title_task is not None and not title_task.done():
                title_task.cancel()  # nothing was persisted; don't title an empty chat
            yield {'type': 'error', 'message': ERROR_MESSAGE}

    async def _run_events(self, run) -> AsyncIterator[dict]:
        """Status and delta events from one agent run, in stream order."""
        async for node in run:
            if Agent.is_model_request_node(node):
                async with node.stream(run.ctx) as request_stream:
                    async for event in self._answer_deltas(request_stream):
                        yield event
            elif Agent.is_call_tools_node(node):
                # Parallel tool calls all announce up front, then execute
                # concurrently; the ids let the client keep one line per call
                # and retire each as its result lands.
                async with node.stream(run.ctx) as tool_stream:
                    async for event in tool_stream:
                        if isinstance(event, FunctionToolCallEvent):
                            yield {
                                'type': 'status',
                                'id': event.part.tool_call_id,
                                'text': status_text(event.part),
                            }
                        elif isinstance(event, FunctionToolResultEvent):
                            yield {'type': 'status_done', 'id': event.part.tool_call_id}

    def _spawn(self, coro: Coroutine[None, None, str | None]) -> asyncio.Task[str | None]:
        """Run coro as a task the service keeps alive past a client disconnect."""
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    @staticmethod
    async def _answer_deltas(request_stream) -> AsyncIterator[dict]:
        """Route streamed model output to thought, delta and demote events.

        Thinking parts are commentary by construction and stream out as
        thought events immediately. Plain text is ambiguous: it is commentary
        exactly when tool calls follow it in the same response, which is
        unknowable while it streams. So text buffers up to TEXT_HOLDBACK
        characters first: a tool call arriving while the buffer holds
        confirms commentary, which flushes as a thought and never flashes as
        answer. Text that overflows the holdback streams as answer deltas,
        with a demote event as the fallback if a tool call follows after all.
        Anything still buffered when the stream ends is answer text.
        """
        buffer: list[str] = []
        streaming_answer = False
        thought_sent = False
        async for event in request_stream:
            part = event.part if isinstance(event, PartStartEvent) else None
            delta = event.delta if isinstance(event, PartDeltaEvent) else None
            if isinstance(part, ThinkingPart) and part.content:
                thought_sent = True
                yield {'type': 'thought', 'text': part.content}
            elif isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                thought_sent = True
                yield {'type': 'thought', 'text': delta.content_delta}
            elif isinstance(part, TextPart) or isinstance(delta, TextPartDelta):
                chunk = delta.content_delta if isinstance(delta, TextPartDelta) else ''
                if isinstance(part, TextPart):
                    chunk = part.content
                if not chunk:
                    continue
                if streaming_answer:
                    yield {'type': 'delta', 'text': chunk}
                    continue
                buffer.append(chunk)
                if sum(map(len, buffer)) >= TEXT_HOLDBACK:
                    streaming_answer = True
                    yield {'type': 'delta', 'text': ''.join(buffer)}
                    buffer.clear()
            elif isinstance(part, ToolCallPart):
                if buffer:
                    text = ('\n' if thought_sent else '') + ''.join(buffer)
                    buffer.clear()
                    thought_sent = True
                    yield {'type': 'thought', 'text': text}
                elif streaming_answer:
                    streaming_answer = False
                    yield {'type': 'demote'}
        if buffer:
            yield {'type': 'delta', 'text': ''.join(buffer)}

    async def _title_chat(self, chat_id: str, user_text: str) -> str | None:
        """Give a fresh chat a short title from its opening message. Best-effort."""
        try:
            agent = Agent(resolve_model(self.settings), instructions=TITLE_INSTRUCTIONS)
            result = await agent.run(user_text)
            title = ' '.join(result.output.split()).strip('"\'').rstrip('.')[:80]
            if not title:
                return None
            await chats.update_title(self.pool, chat_id, title)
            return title
        except Exception:
            logger.exception('title generation failed')
            return None
