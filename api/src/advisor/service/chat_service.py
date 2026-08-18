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
)

from advisor.agents import ADVISOR_SPEC_PATH, CAPABILITY_TYPES
from advisor.agents.capabilities.core import AdvisorDeps, CitationRepo
from advisor.config import Settings, resolve_model
from advisor.service import chats, portfolio_store
from advisor.service.display import status_text

logger = logging.getLogger(__name__)

ERROR_MESSAGE = 'The agent failed to answer. Try again.'

TITLE_INSTRUCTIONS = (
    'Title a conversation that opens with the given message. '
    'Three to six words, plain text, no quotes, no trailing punctuation.'
)


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
        """Forward streamed model output as thought and delta events.

        Thinking parts are reasoning and stream out as thought events for
        the current bubble. Every text part - commentary between tool rounds
        and the answer alike - streams as delta events: text belongs to the
        chat itself and stays there, so nothing needs reclassifying.
        """
        async for event in request_stream:
            part = event.part if isinstance(event, PartStartEvent) else None
            delta = event.delta if isinstance(event, PartDeltaEvent) else None
            if isinstance(part, ThinkingPart) and part.content:
                yield {'type': 'thought', 'text': part.content}
            elif isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                yield {'type': 'thought', 'text': delta.content_delta}
            elif isinstance(part, TextPart) and part.content:
                yield {'type': 'delta', 'text': part.content}
            elif isinstance(delta, TextPartDelta) and delta.content_delta:
                yield {'type': 'delta', 'text': delta.content_delta}

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
