from pathlib import Path

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel

from advisor.agents.capabilities.core import Position, Source
from advisor.config import Settings
from advisor.service import chats, portfolio_store
from advisor.service.chat_service import ChatService

SEED = Path(__file__).parents[2] / 'etc' / 'portfolio.yaml'


def make_service(pool) -> ChatService:
    settings = Settings(model='test', database_url='', portfolio_path=SEED)
    return ChatService(pool=pool, settings=settings)


async def collect(service, chat_id, text):
    return [event async for event in service.stream_reply(chat_id, text)]


async def test_stream_shape_and_persistence(pool):
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    events = await collect(service, chat['id'], 'What do I hold?')
    kinds = [e['type'] for e in events]
    # The title races the answer, so it may land anywhere after the first
    # event; sources then done close the exchange.
    assert 'title' in kinds
    assert kinds.index('sources') < kinds.index('done')
    assert 'delta' in kinds
    assert ''.join(e['text'] for e in events if e['type'] == 'delta')
    exchanges = await chats.get_exchanges(pool, chat['id'])
    assert exchanges[0]['user_text'] == 'What do I hold?'
    # Display parts rebuild from the stored batch: the tool round became a
    # bubble and the last part carries the processed answer.
    parts = exchanges[0]['parts']
    tool_lines = [t['text'] for p in parts if p['kind'] == 'bubble' for t in p['tools']]
    assert 'Reading the portfolio' in tool_lines
    assert parts[-1] == {'kind': 'text', 'text': exchanges[0]['assistant_text']}


async def test_status_events_surface_tool_calls_and_retire(pool):
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    events = await collect(service, chat['id'], 'What do I hold?')
    statuses = [e for e in events if e['type'] == 'status']
    assert 'Reading the portfolio' in [e['text'] for e in statuses]  # TestModel calls every tool
    done_ids = [e['id'] for e in events if e['type'] == 'status_done']
    for status in statuses:  # every announced call reports completion
        assert status['id'] in done_ids
    sources_event = next(e for e in events if e['type'] == 'sources')
    assert sources_event['text']


async def test_first_message_titles_chat(pool):
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    events = await collect(service, chat['id'], 'Should I trim NVDA?')
    titles = [e['title'] for e in events if e['type'] == 'title']
    assert titles
    assert (await chats.list_chats(pool))[0]['title'] == titles[0]
    followup = await collect(service, chat['id'], 'And MSFT?')
    assert not [e for e in followup if e['type'] == 'title']


async def test_title_survives_client_disconnect(pool):
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    stream = service.stream_reply(chat['id'], 'What do I hold?')
    async for event in stream:
        if event['type'] == 'done':
            break
    await stream.aclose()  # client walks away before the title event
    for task in list(service._background):
        await task
    assert (await chats.list_chats(pool))[0]['title'] != 'New conversation'


async def test_multiturn_history_grows(pool):
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    await collect(service, chat['id'], 'first')
    await collect(service, chat['id'], 'second')
    history = await chats.get_model_history(pool, chat['id'])
    assert len(history) >= 4


async def test_text_streams_as_deltas_in_stream_order():
    """All text - commentary before tool calls and answer alike - streams
    as deltas: text belongs to the chat and stays there."""

    async def commentary_round():
        yield PartStartEvent(index=0, part=TextPart(content='Let me '))
        yield PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='search.'))
        yield PartStartEvent(index=1, part=ToolCallPart(tool_name='web_search'))

    events = [e async for e in ChatService._answer_deltas(commentary_round())]
    assert events == [
        {'type': 'delta', 'text': 'Let me '},
        {'type': 'delta', 'text': 'search.'},
    ]


async def test_thinking_streams_as_thought_events():
    """Thinking parts stream as thought events for the bubbles; text in the
    same round streams as deltas for the chat."""

    async def reasoning_round():
        yield PartStartEvent(index=0, part=ThinkingPart(content='The user wants '))
        yield PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta='a comparison.'))
        yield PartStartEvent(index=1, part=TextPart(content='Running searches.'))
        yield PartStartEvent(index=2, part=ToolCallPart(tool_name='web_search'))

    events = [e async for e in ChatService._answer_deltas(reasoning_round())]
    assert events == [
        {'type': 'thought', 'text': 'The user wants '},
        {'type': 'thought', 'text': 'a comparison.'},
        {'type': 'delta', 'text': 'Running searches.'},
    ]


async def test_portfolio_edits_reach_the_next_message(pool):
    """The agent reads the portfolio from the database per message, so an
    edit made between messages shows up in the tool result."""
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    await portfolio_store.upsert_position(
        pool, Position(ticker='ZZZT', name='Zeta Test', quantity=5, cost_basis=10, currency='USD')
    )
    events = await collect(service, chat['id'], 'What do I hold?')
    sources_event = next(e for e in events if e['type'] == 'sources')
    assert 'ZZZT' in sources_event['text']  # TestModel echoes the tool result


async def test_follow_up_keeps_prior_turn_citations(pool, monkeypatch):
    """A later answer may cite a source registered on an earlier turn: the
    repo is seeded from the chat's persisted citation state, so the marker
    survives and the source rides along with the new exchange."""
    service = make_service(pool)
    chat = await chats.create_chat(pool)
    state = [Source(id=1, title='NVDA Q2', url='https://news.example/nvda')]
    first_turn = ModelMessagesTypeAdapter.dump_json(
        [ModelRequest(parts=[UserPromptPart(content='news?')])]
    )
    await chats.append_exchange(
        pool, chat['id'], 'news?', 'NVDA beat [1].', state, first_turn, citation_state=state
    )
    monkeypatch.setattr(
        'advisor.service.chat_service.resolve_model',
        lambda settings, test_call_tools='all': TestModel(
            call_tools=[], custom_output_text='Still true [1].'
        ),
    )
    events = await collect(service, chat['id'], 'still true?')
    sources_event = next(e for e in events if e['type'] == 'sources')
    assert sources_event['text'] == 'Still true [1].'
    assert [s['url'] for s in sources_event['sources']] == ['https://news.example/nvda']
    exchanges = await chats.get_exchanges(pool, chat['id'])
    assert exchanges[-1]['assistant_text'] == 'Still true [1].'
    assert exchanges[-1]['sources'] == state


async def test_error_yields_error_event_and_no_row(pool, monkeypatch):
    service = make_service(pool)
    chat = await chats.create_chat(pool)

    def boom(*args, **kwargs):
        raise RuntimeError('kaput')

    monkeypatch.setattr('advisor.service.chat_service.resolve_model', boom)
    events = await collect(service, chat['id'], 'hi')
    assert events == [{'type': 'error', 'message': 'The agent failed to answer. Try again.'}]
    assert await chats.get_exchanges(pool, chat['id']) == []
