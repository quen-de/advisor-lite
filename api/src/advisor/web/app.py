import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from advisor.agents.capabilities.core import Position
from advisor.agents.capabilities.portfolio import load_portfolio, portfolio_summary
from advisor.config import Settings
from advisor.service import chats, portfolio_store
from advisor.service.chat_service import ChatService
from advisor.service.db import apply_schema, create_pool


def sse_event(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data)}\n\n'


class MessageIn(BaseModel):
    content: str


class PositionIn(BaseModel):
    name: str
    quantity: float = Field(ge=0)
    cost_basis: float = Field(ge=0)
    currency: str


class CashIn(BaseModel):
    cash: float = Field(ge=0)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = await create_pool(resolved.database_url)
        await apply_schema(pool)
        await portfolio_store.seed_if_empty(pool, load_portfolio(resolved.portfolio_path))
        app.state.pool = pool
        app.state.chat_service = ChatService(pool=pool, settings=resolved)
        yield
        await pool.close()

    app = FastAPI(title='advisor-lite', lifespan=lifespan)

    @app.get('/api/healthz')
    async def healthz(request: Request):
        await request.app.state.pool.fetchval('select 1')
        return {'status': 'ok'}

    @app.get('/api/portfolio')
    async def portfolio(request: Request):
        p = await portfolio_store.get_portfolio(request.app.state.pool)
        assert p is not None  # seeded at startup
        return {**p.model_dump(mode='json'), 'summary': portfolio_summary(p)}

    @app.put('/api/positions/{ticker}', status_code=204)
    async def put_position(request: Request, ticker: str, body: PositionIn) -> None:
        position = Position(ticker=ticker.upper(), **body.model_dump())
        await portfolio_store.upsert_position(request.app.state.pool, position)

    @app.delete('/api/positions/{ticker}', status_code=204)
    async def remove_position(request: Request, ticker: str) -> None:
        await portfolio_store.delete_position(request.app.state.pool, ticker.upper())

    @app.patch('/api/portfolio', status_code=204)
    async def patch_portfolio(request: Request, body: CashIn) -> None:
        await portfolio_store.set_cash(request.app.state.pool, body.cash)

    @app.post('/api/chats')
    async def create_chat(request: Request):
        return await chats.create_chat(request.app.state.pool)

    @app.get('/api/chats')
    async def list_chats(request: Request):
        return await chats.list_chats(request.app.state.pool)

    @app.delete('/api/chats/{chat_id}', status_code=204)
    async def delete_chat(request: Request, chat_id: str) -> None:
        await chats.delete_chat(request.app.state.pool, chat_id)

    @app.get('/api/chats/{chat_id}/exchanges')
    async def exchanges(request: Request, chat_id: str):
        return await chats.get_exchanges(request.app.state.pool, chat_id)

    @app.post('/api/chats/{chat_id}/messages')
    async def send_message(request: Request, chat_id: str, message: MessageIn):
        service: ChatService = request.app.state.chat_service

        async def stream():
            async for event in service.stream_reply(chat_id, message.content):
                yield sse_event(event.pop('type'), event)

        return StreamingResponse(stream(), media_type='text/event-stream')

    return app
