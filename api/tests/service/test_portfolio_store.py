from datetime import date
from pathlib import Path

from advisor.agents.capabilities.core import Position
from advisor.agents.capabilities.portfolio import load_portfolio
from advisor.service import portfolio_store

SEED = Path(__file__).parents[2] / 'etc' / 'portfolio.yaml'


async def test_seed_round_trips_and_is_idempotent(pool):
    seed = load_portfolio(SEED)
    stored = await portfolio_store.get_portfolio(pool)
    assert stored is not None
    assert stored.cash == seed.cash
    assert [p.ticker for p in stored.positions] == [p.ticker for p in seed.positions]
    await portfolio_store.seed_if_empty(pool, seed)  # second boot: no duplicates
    again = await portfolio_store.get_portfolio(pool)
    assert again is not None
    assert len(again.positions) == len(seed.positions)


async def test_upsert_adds_then_updates_and_moves_as_of(pool):
    position = Position(ticker='ZZZT', name='Zeta', quantity=5, cost_basis=10, currency='USD')
    await portfolio_store.upsert_position(pool, position)
    stored = await portfolio_store.get_portfolio(pool)
    assert stored is not None
    assert stored.as_of == date.today()
    assert any(p.ticker == 'ZZZT' and p.quantity == 5 for p in stored.positions)
    await portfolio_store.upsert_position(pool, position.model_copy(update={'quantity': 8}))
    stored = await portfolio_store.get_portfolio(pool)
    assert stored is not None
    (zeta,) = [p for p in stored.positions if p.ticker == 'ZZZT']
    assert zeta.quantity == 8


async def test_delete_position(pool):
    stored = await portfolio_store.get_portfolio(pool)
    assert stored is not None
    first = stored.positions[0].ticker
    await portfolio_store.delete_position(pool, first)
    after = await portfolio_store.get_portfolio(pool)
    assert after is not None
    assert first not in [p.ticker for p in after.positions]


async def test_set_cash(pool):
    await portfolio_store.set_cash(pool, 1234.5)
    stored = await portfolio_store.get_portfolio(pool)
    assert stored is not None
    assert stored.cash == 1234.5
