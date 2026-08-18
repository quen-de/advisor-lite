from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    UserPromptPart,
)

from advisor.service.display import display_parts, status_text


def test_status_text_names_known_tools():
    assert status_text(ToolCallPart(tool_name='get_portfolio')) == 'Reading the portfolio'
    part = ToolCallPart(tool_name='web_search', args={'query': 'NVDA news'})
    assert status_text(part) == 'Searching the web for "NVDA news"'
    assert status_text(ToolCallPart(tool_name='other')) == 'Running other'


def test_display_parts_rebuilds_the_live_transcript():
    """Bubbles and text segments come back in stream order, with the final
    raw text replaced by the citation-processed answer."""
    messages = [
        ModelRequest(parts=[UserPromptPart(content='diversify?')]),
        ModelResponse(
            parts=[
                ThinkingPart(content='Check holdings '),
                ThinkingPart(content='first.'),
                ToolCallPart(tool_name='get_portfolio'),
            ]
        ),
        ModelRequest(parts=[]),
        ModelResponse(
            parts=[
                TextPart(content='The book is tech-heavy.'),
                ToolCallPart(tool_name='web_search', args={'query': 'diversifiers'}),
            ]
        ),
        ModelRequest(parts=[]),
        ModelResponse(parts=[TextPart(content='Raw answer [1][9].')]),
    ]
    assert display_parts(messages, 'Answer [1].') == [
        {
            'kind': 'bubble',
            'thoughts': 'Check holdings first.',
            'tools': [{'text': 'Reading the portfolio', 'done': True}],
        },
        {'kind': 'text', 'text': 'The book is tech-heavy.'},
        {
            'kind': 'bubble',
            'thoughts': '',
            'tools': [{'text': 'Searching the web for "diversifiers"', 'done': True}],
        },
        {'kind': 'text', 'text': 'Answer [1].'},
    ]


def test_display_parts_without_text_appends_the_answer():
    messages: list[ModelMessage] = [ModelResponse(parts=[ToolCallPart(tool_name='get_portfolio')])]
    assert display_parts(messages, 'Answer.')[-1] == {'kind': 'text', 'text': 'Answer.'}
