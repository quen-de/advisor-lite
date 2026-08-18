from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from advisor.agents.capabilities.core import AdvisorDeps
from advisor.agents.capabilities.portfolio import (
    PortfolioCapability,
    load_portfolio,
    portfolio_summary,
)

SEED = Path(__file__).parents[2] / 'etc' / 'portfolio.yaml'


def test_load_portfolio_parses_seed():
    p = load_portfolio(SEED)
    assert p.currency == 'USD'
    assert {pos.ticker for pos in p.positions} >= {'NVDA', 'MSFT'}


def test_summary_contains_weights():
    p = load_portfolio(SEED)
    text = portfolio_summary(p)
    assert 'NVDA' in text and '%' in text and 'cash' in text.lower()


async def test_capability_tool_returns_summary():
    p = load_portfolio(SEED)
    agent = Agent(
        TestModel(),
        name='t',
        deps_type=AdvisorDeps,
        capabilities=[PortfolioCapability()],
    )
    result = await agent.run('what do I hold?', deps=AdvisorDeps(portfolio=p))
    assert any('NVDA' in str(m) for m in result.all_messages())
