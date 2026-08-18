import os
from pathlib import Path

import asyncpg
import pytest

from advisor.agents.capabilities.portfolio import load_portfolio
from advisor.service import portfolio_store
from advisor.service.db import apply_schema, create_pool

SEED = Path(__file__).parents[2] / 'etc' / 'portfolio.yaml'


@pytest.fixture
async def pool():
    """Pool on a disposable test database, created on first use.

    The suite truncates tables, so it refuses to run against anything that
    does not look like a test database: the name must end in `_test`. This
    keeps a dev stack's conversations safe from a local pytest run.
    """
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL not set')
    base, _, name = url.rpartition('/')
    name = name.partition('?')[0]
    if not name.endswith('_test'):
        pytest.fail(
            f'TEST_DATABASE_URL points at {name!r}. The suite truncates tables, '
            "so the database name must end in '_test' (it is created if missing), "
            'e.g. postgresql://advisor:advisor@localhost:5432/advisor_test'
        )
    try:
        pool = await create_pool(url)
    except asyncpg.InvalidCatalogNameError:
        admin = await asyncpg.connect(f'{base}/postgres')
        await admin.execute(f'create database "{name}"')
        await admin.close()
        pool = await create_pool(url)
    await apply_schema(pool)
    async with pool.acquire() as conn:
        await conn.execute('truncate exchanges, chats, portfolio, positions')
    await portfolio_store.seed_if_empty(pool, load_portfolio(SEED))
    yield pool
    await pool.close()
