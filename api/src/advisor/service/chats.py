import json
from typing import TypedDict

import asyncpg
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from advisor.agents.capabilities.core import Source


class ChatRow(TypedDict):
    id: str
    title: str
    created_at: str


class ExchangeRow(TypedDict):
    user_text: str
    assistant_text: str
    sources: list[Source]


async def create_chat(pool: asyncpg.Pool, title: str = 'New conversation') -> ChatRow:
    row = await pool.fetchrow(
        'insert into chats (title) values ($1) returning id, title, created_at', title
    )
    assert row is not None
    return ChatRow(id=str(row['id']), title=row['title'], created_at=row['created_at'].isoformat())


async def list_chats(pool: asyncpg.Pool) -> list[ChatRow]:
    rows = await pool.fetch('select id, title, created_at from chats order by created_at desc')
    return [
        ChatRow(id=str(r['id']), title=r['title'], created_at=r['created_at'].isoformat())
        for r in rows
    ]


async def update_title(pool: asyncpg.Pool, chat_id: str, title: str) -> None:
    await pool.execute('update chats set title = $1 where id = $2', title, chat_id)


async def delete_chat(pool: asyncpg.Pool, chat_id: str) -> None:
    """Delete a chat; exchanges follow via the FK cascade."""
    await pool.execute('delete from chats where id = $1', chat_id)


async def get_exchanges(pool: asyncpg.Pool, chat_id: str) -> list[ExchangeRow]:
    rows = await pool.fetch(
        'select user_text, assistant_text, sources from exchanges where chat_id = $1 order by id',
        chat_id,
    )
    return [
        ExchangeRow(
            user_text=r['user_text'],
            assistant_text=r['assistant_text'],
            sources=json.loads(r['sources']),
        )
        for r in rows
    ]


async def get_citations(pool: asyncpg.Pool, chat_id: str) -> list[Source]:
    """The chat's accumulated citation state: every source registered so far."""
    value = await pool.fetchval('select citations from chats where id = $1', chat_id)
    return json.loads(value) if value else []


async def get_model_history(pool: asyncpg.Pool, chat_id: str) -> list[ModelMessage]:
    """Concatenate every stored message batch for the chat, oldest first."""
    rows = await pool.fetch(
        'select model_messages from exchanges where chat_id = $1 order by id', chat_id
    )
    history: list[ModelMessage] = []
    for r in rows:
        history.extend(ModelMessagesTypeAdapter.validate_json(r['model_messages']))
    return history


async def append_exchange(
    pool: asyncpg.Pool,
    chat_id: str,
    user_text: str,
    assistant_text: str,
    sources: list[Source],
    model_messages_json: bytes,
    citation_state: list[Source] | None = None,
) -> None:
    """Store one exchange; `citation_state`, when given, replaces the chat's
    accumulated citation state in the same transaction."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            'insert into exchanges (chat_id, user_text, assistant_text, sources, model_messages) '
            'values ($1, $2, $3, $4, $5)',
            chat_id,
            user_text,
            assistant_text,
            json.dumps(sources),
            model_messages_json.decode(),
        )
        if citation_state is not None:
            await conn.execute(
                'update chats set citations = $1 where id = $2',
                json.dumps(citation_state),
                chat_id,
            )
