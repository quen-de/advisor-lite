from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart

from advisor.agents.capabilities.core import Source
from advisor.service import chats


def messages_json() -> bytes:
    messages = [ModelRequest(parts=[UserPromptPart(content='hi')])]
    return ModelMessagesTypeAdapter.dump_json(messages)


async def test_create_and_list(pool):
    row = await chats.create_chat(pool)
    assert (await chats.list_chats(pool))[0]['id'] == row['id']


async def test_append_and_read_exchange(pool):
    row = await chats.create_chat(pool)
    await chats.append_exchange(
        pool,
        row['id'],
        'hello',
        'answer [1]',
        [{'id': 1, 'title': 'T', 'url': 'https://u'}],
        messages_json(),
    )
    exchanges = await chats.get_exchanges(pool, row['id'])
    assert exchanges[0]['assistant_text'] == 'answer [1]'
    assert exchanges[0]['sources'][0]['url'] == 'https://u'


async def test_model_history_concatenates(pool):
    row = await chats.create_chat(pool)
    for _ in range(2):
        await chats.append_exchange(pool, row['id'], 'q', 'a', [], messages_json())
    history = await chats.get_model_history(pool, row['id'])
    assert len(history) == 2


async def test_citation_state_persists_with_the_chat(pool):
    row = await chats.create_chat(pool)
    assert await chats.get_citations(pool, row['id']) == []
    state = [
        Source(id=1, title='T', url='https://u'),
        Source(id=2, title='Uncited but registered', url='https://v'),
    ]
    await chats.append_exchange(
        pool, row['id'], 'q', 'a [1]', state[:1], messages_json(), citation_state=state
    )
    assert await chats.get_citations(pool, row['id']) == state


async def test_update_title(pool):
    row = await chats.create_chat(pool)
    await chats.update_title(pool, row['id'], 'Trim NVDA?')
    assert (await chats.list_chats(pool))[0]['title'] == 'Trim NVDA?'


async def test_delete_chat_cascades(pool):
    row = await chats.create_chat(pool)
    await chats.append_exchange(pool, row['id'], 'q', 'a', [], messages_json())
    await chats.delete_chat(pool, row['id'])
    assert await chats.list_chats(pool) == []
    assert await chats.get_exchanges(pool, row['id']) == []


async def test_schema_idempotent(pool):
    from advisor.service.db import apply_schema

    await apply_schema(pool)
