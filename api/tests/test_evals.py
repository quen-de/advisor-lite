from pathlib import Path

from pydantic_evals import Case, Dataset

from evals.run import EVALUATOR_TYPES, Answer, Cites, Declines, Mentions

DATASET = Path(__file__).parents[1] / 'evals' / 'dataset.yaml'

SOURCE = {'id': 1, 'title': 'T', 'url': 'https://u'}


def canned(text: str, sources: list | None = None):
    async def task(prompt: str) -> Answer:
        return Answer(text=text, sources=sources or [])

    return task


def single_case(evaluator) -> Dataset[str, Answer]:
    return Dataset[str, Answer](
        name='t', cases=[Case(name='c', inputs='q', evaluators=(evaluator,))]
    )


async def verdict(evaluator, text: str, sources: list | None = None) -> bool:
    report = await single_case(evaluator).evaluate(canned(text, sources), progress=False)
    (result,) = report.cases[0].assertions.values()
    return result.value


async def test_cites_needs_marker_and_source():
    assert await verdict(Cites(), 'NVDA fell [1].', [SOURCE])
    assert not await verdict(Cites(), 'no marker', [])
    assert not await verdict(Cites(), 'marker only [1]', [])


async def test_mentions_matches_any_term_case_insensitively():
    assert await verdict(Mentions(any_of=['NVDA', 'MSFT']), 'NVDA is your largest position')
    assert await verdict(Mentions(any_of=['NVDA', 'MSFT']), 'holding msft steady')
    assert not await verdict(Mentions(any_of=['NVDA', 'MSFT']), 'nothing relevant')


async def test_declines_detects_refusals():
    assert await verdict(Declines(), 'I cannot place orders.')
    assert await verdict(Declines(), "I can't help with tax advice.")
    assert not await verdict(Declines(), 'Here is how to do it.')


def test_dataset_file_loads_with_the_custom_evaluators():
    dataset = Dataset[str, Answer].from_file(DATASET, custom_evaluator_types=EVALUATOR_TYPES)
    assert len(dataset.cases) == 4
    assert all(case.evaluators for case in dataset.cases)
