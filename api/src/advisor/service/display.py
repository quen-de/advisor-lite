"""Presentation of a model run: progress lines and the persisted transcript.

The chat view renders an assistant message as an ordered list of parts:
thinking bubbles (the model's reasoning plus the tool calls it made) and
text segments (commentary between tool rounds, then the answer). Live runs
build that list from stream events; on reload it is rebuilt here from the
exchange's stored model messages, so nothing shown live is lost to a refresh.
"""

from dataclasses import dataclass, field

from pydantic_ai.messages import ModelMessage, ModelResponse, ThinkingPart, ToolCallPart


@dataclass
class _Segment:
    kind: str  # 'bubble' | 'text'
    thoughts: str = ''
    text: str = ''
    tools: list[dict] = field(default_factory=list)


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


def display_parts(messages: list[ModelMessage], assistant_text: str) -> list[dict]:
    """Rebuild a message's display parts from its stored model messages.

    Mirrors what the client assembled live: thinking parts open or extend a
    bubble, tool calls stack into the current bubble, text parts become text
    segments. The last text segment is the raw final output, so it is
    replaced by the citation-processed `assistant_text` the exchange stored.
    """
    segments: list[_Segment] = []
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            last = segments[-1] if segments else None
            if isinstance(part, ThinkingPart):
                if not part.content:
                    continue
                if last and last.kind == 'bubble' and not last.tools:
                    last.thoughts += part.content
                else:
                    segments.append(_Segment('bubble', thoughts=part.content))
            elif isinstance(part, ToolCallPart):
                if not (last and last.kind == 'bubble'):
                    last = _Segment('bubble')
                    segments.append(last)
                last.tools.append({'text': status_text(part), 'done': True})
            elif part.part_kind == 'text' and part.content:
                if last and last.kind == 'text':
                    last.text += part.content
                else:
                    segments.append(_Segment('text', text=part.content))
    if segments and segments[-1].kind == 'text':
        segments[-1].text = assistant_text
    else:
        segments.append(_Segment('text', text=assistant_text))
    return [
        {'kind': 'bubble', 'thoughts': s.thoughts, 'tools': s.tools}
        if s.kind == 'bubble'
        else {'kind': 'text', 'text': s.text}
        for s in segments
    ]
