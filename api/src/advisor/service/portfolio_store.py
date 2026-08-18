"""DB-backed portfolio: one demo portfolio, seeded from yaml on first boot.

After seeding, the database is canonical; edits from the web view land here
and every agent run reads the current state. Any mutation moves `as_of` to
today, since the data now reflects that day's holdings.
"""

from datetime import date

import asyncpg

from advisor.agents.capabilities.core import Portfolio, Position


async def get_portfolio(pool: asyncpg.Pool) -> Portfolio | None:
    meta = await pool.fetchrow('select cash, currency, as_of from portfolio')
    if meta is None:
        return None
    rows = await pool.fetch(
        'select ticker, name, quantity, cost_basis, currency from positions order by id'
    )
    return Portfolio(
        as_of=meta['as_of'],
        cash=meta['cash'],
        currency=meta['currency'],
        positions=[Position(**dict(r)) for r in rows],
    )


async def seed_if_empty(pool: asyncpg.Pool, seed: Portfolio) -> None:
    async with pool.acquire() as conn, conn.transaction():
        if await conn.fetchval('select true from portfolio') is not None:
            return
        await conn.execute(
            'insert into portfolio (cash, currency, as_of) values ($1, $2, $3)',
            seed.cash,
            seed.currency,
            seed.as_of,
        )
        for pos in seed.positions:
            await conn.execute(
                'insert into positions (ticker, name, quantity, cost_basis, currency) '
                'values ($1, $2, $3, $4, $5)',
                pos.ticker,
                pos.name,
                pos.quantity,
                pos.cost_basis,
                pos.currency,
            )


async def upsert_position(pool: asyncpg.Pool, position: Position) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            'insert into positions (ticker, name, quantity, cost_basis, currency) '
            'values ($1, $2, $3, $4, $5) '
            'on conflict (ticker) do update set '
            'name = excluded.name, quantity = excluded.quantity, '
            'cost_basis = excluded.cost_basis, currency = excluded.currency',
            position.ticker,
            position.name,
            position.quantity,
            position.cost_basis,
            position.currency,
        )
        await conn.execute('update portfolio set as_of = $1', date.today())


async def delete_position(pool: asyncpg.Pool, ticker: str) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('delete from positions where ticker = $1', ticker)
        await conn.execute('update portfolio set as_of = $1', date.today())


async def set_cash(pool: asyncpg.Pool, cash: float) -> None:
    await pool.execute('update portfolio set cash = $1, as_of = $2', cash, date.today())
