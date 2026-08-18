from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai import RunContext, Tool
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from advisor.agents.capabilities.core import AdvisorDeps, Portfolio


def load_portfolio(path: Path) -> Portfolio:
    """Parse a portfolio seed file."""
    return Portfolio.model_validate(yaml.safe_load(path.read_text()))


def portfolio_summary(p: Portfolio) -> str:
    """Render the portfolio as a markdown table with cost-basis weights."""
    values = {pos.ticker: pos.quantity * pos.cost_basis for pos in p.positions}
    total = sum(values.values()) + p.cash

    def weight(value: float) -> str:
        return f'{value / total:.1%}' if total else '-'

    lines = [
        f'Demo portfolio as of {p.as_of} (cost-basis valuation, {p.currency} nominal):',
        '',
        '| Ticker | Name | Qty | Cost basis | Value | Weight |',
        '|---|---|---|---|---|---|',
    ]
    for pos in p.positions:
        value = values[pos.ticker]
        lines.append(
            f'| {pos.ticker} | {pos.name} | {pos.quantity:g} | '
            f'{pos.cost_basis:.2f} {pos.currency} | {value:,.0f} | {weight(value)} |'
        )
    lines.append(f'| cash | - | - | - | {p.cash:,.0f} | {weight(p.cash)} |')
    return '\n'.join(lines)


INSTRUCTIONS = (
    "You advise on the user's demo portfolio. Call get_portfolio before answering "
    'any question about holdings, weights, or exposure. Valuations are cost-basis '
    'demo data; say so when precision matters.'
)


async def get_portfolio(ctx: RunContext[AdvisorDeps]) -> str:
    """Return the user's current portfolio: positions, cost basis, weights, cash."""
    return portfolio_summary(ctx.deps.portfolio)


@dataclass
class PortfolioCapability(AbstractCapability[AdvisorDeps]):
    @classmethod
    def get_serialization_name(cls) -> str:
        return 'portfolio'

    def get_instructions(self) -> str:
        return INSTRUCTIONS

    def get_toolset(self) -> FunctionToolset[AdvisorDeps]:
        return FunctionToolset([Tool[AdvisorDeps](get_portfolio, takes_ctx=True)], id='portfolio')
