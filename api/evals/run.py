"""Score the advisor agent against the pydantic-evals dataset next to this file.

Run from api/:

    uv run python -m evals.run
"""

import argparse
import asyncio
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from advisor.agents import ADVISOR_SPEC_PATH, CAPABILITY_TYPES
from advisor.agents.capabilities.core import AdvisorDeps, CitationRepo, Source
from advisor.agents.capabilities.portfolio import load_portfolio
from advisor.config import Settings, resolve_model

PASS_THRESHOLD = 0.8

DECLINE_WORDS = ('cannot', "can't", 'not able', 'demo')

MARKER = re.compile(r'\[\d+\]')


class Answer(BaseModel):
    """What one agent run produced: the processed text and the cited sources."""

    text: str
    sources: list[Source]


@dataclass
class Cites(Evaluator[str, Answer]):
    """The answer carries at least one marker backed by a referenced source."""

    def evaluate(self, ctx: EvaluatorContext[str, Answer]) -> bool:
        return bool(ctx.output.sources) and bool(MARKER.search(ctx.output.text))


@dataclass
class Mentions(Evaluator[str, Answer]):
    """The answer names at least one of the expected terms."""

    any_of: list[str]

    def evaluate(self, ctx: EvaluatorContext[str, Answer]) -> bool:
        lowered = ctx.output.text.lower()
        return any(term.lower() in lowered for term in self.any_of)


@dataclass
class Declines(Evaluator[str, Answer]):
    """The answer refuses rather than plays along."""

    def evaluate(self, ctx: EvaluatorContext[str, Answer]) -> bool:
        lowered = ctx.output.text.lower()
        return any(word in lowered for word in DECLINE_WORDS)


EVALUATOR_TYPES = (Cites, Mentions, Declines)


def make_task(settings: Settings) -> Callable[[str], Awaitable[Answer]]:
    portfolio = load_portfolio(settings.portfolio_path)

    async def answer(prompt: str) -> Answer:
        agent = Agent.from_file(
            ADVISOR_SPEC_PATH,
            deps_type=AdvisorDeps,
            custom_capability_types=CAPABILITY_TYPES,
            model=resolve_model(settings, test_call_tools=['get_portfolio']),
        )
        deps = AdvisorDeps(portfolio=portfolio, citations=CitationRepo())
        result = await agent.run(prompt, deps=deps)
        return Answer(text=result.output, sources=deps.citations.referenced)

    return answer


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=Path(__file__).parent / 'dataset.yaml')
    parser.add_argument('--summary', type=Path, default=None)
    args = parser.parse_args()

    settings = Settings.from_env()
    dataset = Dataset[str, Answer].from_file(args.dataset, custom_evaluator_types=EVALUATOR_TYPES)
    report = await dataset.evaluate(make_task(settings), progress=False)

    # Gate on the dataset's full check count: a case that errors out contributes
    # zero passing assertions instead of shrinking the denominator.
    expected = sum(len(case.evaluators) for case in dataset.cases) + len(dataset.evaluators) * len(
        dataset.cases
    )
    passed = sum(a.value for case in report.cases for a in case.assertions.values())
    rate = passed / expected if expected else 0.0
    table = report.render(include_averages=True)
    verdict = f'{passed}/{expected} checks passed ({rate:.0%}, threshold {PASS_THRESHOLD:.0%})'
    print(table)
    print(verdict)
    if args.summary:
        args.summary.write_text(f'```\n{table}\n```\n\n**{verdict}**\n')
    return 0 if rate >= PASS_THRESHOLD else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
