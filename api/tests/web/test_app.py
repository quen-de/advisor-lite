import os
from pathlib import Path

import asyncpg
import httpx
import pytest
from asgi_lifespan import LifespanManager

from advisor.config import Settings
from advisor.web.app import create_app, sse_event


def test_sse_format():
    assert sse_event('delta', {'text': 'hi'}) == 'event: delta\ndata: {"text": "hi"}\n\n'

SEED = Path(__file__).parents[2] / 'etc' / 'portfolio.yaml'


async def reset_portfolio(url: str) -> None:
    """Startup seeds only an empty portfolio; clear it so each run reseeds."""
    conn = await asyncpg.connect(url)
    try:
        await conn.execute('truncate portfolio, positions')
    except asyncpg.UndefinedTableError:
        pass  # first ever run: startup creates and seeds them
    finally:
        await conn.close()


@pytest.fixture
async def client():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL not set')
    await reset_portfolio(url)
    settings = Settings(model='test', database_url=url, portfolio_path=SEED)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
            yield c


async def test_healthz(client):
    response = await client.get('/api/healthz')
    assert response.status_code == 200 and response.json() == {'status': 'ok'}


async def test_portfolio(client):
    body = (await client.get('/api/portfolio')).json()
    assert body['currency'] == 'USD' and 'NVDA' in body['summary']


async def test_edit_portfolio_via_api(client):
    body = {'name': 'Zeta Test', 'quantity': 5, 'cost_basis': 10, 'currency': 'USD'}
    assert (await client.put('/api/positions/zzzt', json=body)).status_code == 204
    portfolio = (await client.get('/api/portfolio')).json()
    assert any(p['ticker'] == 'ZZZT' for p in portfolio['positions'])  # upper-cased
    assert 'ZZZT' in portfolio['summary']

    assert (await client.patch('/api/portfolio', json={'cash': 42.0})).status_code == 204
    assert (await client.get('/api/portfolio')).json()['cash'] == 42.0

    assert (await client.delete('/api/positions/ZZZT')).status_code == 204
    portfolio = (await client.get('/api/portfolio')).json()
    assert all(p['ticker'] != 'ZZZT' for p in portfolio['positions'])


async def test_rejects_negative_quantity(client):
    body = {'name': 'Bad', 'quantity': -1, 'cost_basis': 10, 'currency': 'USD'}
    assert (await client.put('/api/positions/bad', json=body)).status_code == 422


async def test_delete_chat(client):
    chat = (await client.post('/api/chats')).json()
    response = await client.delete(f'/api/chats/{chat["id"]}')
    assert response.status_code == 204
    ids = [c['id'] for c in (await client.get('/api/chats')).json()]
    assert chat['id'] not in ids


async def test_chat_message_streams_sse(client):
    chat = (await client.post('/api/chats')).json()
    async with client.stream(
        'POST', f'/api/chats/{chat["id"]}/messages', json={'content': 'hi'}
    ) as response:
        assert response.headers['content-type'].startswith('text/event-stream')
        payload = ''.join([chunk async for chunk in response.aiter_text()])
    assert 'event: sources' in payload and 'event: done' in payload
    exchanges = (await client.get(f'/api/chats/{chat["id"]}/exchanges')).json()
    assert len(exchanges) == 1
