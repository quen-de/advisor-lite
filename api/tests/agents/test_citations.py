from pydantic_ai import Agent
from pydantic_ai.messages import ToolReturn
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from advisor.agents.capabilities.citations import CitationsCapability, process_citations
from advisor.agents.capabilities.core import AdvisorDeps, CitationRepo, Portfolio, Source


def deps_with(repo: CitationRepo) -> AdvisorDeps:
    portfolio = Portfolio(as_of='2026-08-01', cash=0, currency='USD', positions=[])
    return AdvisorDeps(portfolio=portfolio, citations=repo)


def test_register_dedupes_by_url():
    repo = CitationRepo()
    a = repo.register('Title A', 'https://x.com/a')
    b = repo.register('Other title, same url', 'https://x.com/a')
    c = repo.register('Title C', 'https://x.com/c')
    assert (a, b, c) == (1, 1, 2)


def test_seeded_repo_resolves_prior_turn_ids_and_continues_numbering():
    known = [
        Source(id=1, title='A', url='https://x.com/a'),
        Source(id=2, title='B', url='https://x.com/b'),
    ]
    repo = CitationRepo(known)
    text, sources = process_citations('Still true [2].', repo)
    assert text == 'Still true [2].'
    assert [s['id'] for s in sources] == [2]
    assert repo.register('B again', 'https://x.com/b') == 2
    assert repo.register('C', 'https://x.com/c') == 3


def test_process_keeps_valid_markers_and_referenced_sources():
    repo = CitationRepo()
    repo.register('A', 'https://x.com/a')
    repo.register('B', 'https://x.com/b')
    text, sources = process_citations('NVDA fell 3% [1]. Rates held [9].', repo)
    assert text == 'NVDA fell 3% [1]. Rates held.'
    assert [s['id'] for s in sources] == [1]


def test_unreferenced_sources_dropped():
    repo = CitationRepo()
    repo.register('A', 'https://x.com/a')
    _, sources = process_citations('No citations here.', repo)
    assert sources == []


async def test_tool_sources_register_and_flow_to_the_answer():
    """A search-shaped tool reports sources via ToolReturn metadata; the
    capability assigns ids, shows them to the model, and keeps only cited ones."""
    toolset = FunctionToolset[AdvisorDeps](id='stub-search')

    async def web_search(query: str) -> ToolReturn:
        """Stub search returning one source."""
        return ToolReturn(
            'Excerpt about NVDA.',
            metadata={'sources': [{'url': 'https://news.example/nvda', 'title': 'NVDA Q2'}]},
        )

    toolset.add_function(web_search, name='web_search')
    agent = Agent(
        TestModel(custom_output_text='NVDA beat [1]. Bogus [9].'),
        name='t',
        deps_type=AdvisorDeps,
        toolsets=[toolset],
        capabilities=[CitationsCapability()],
    )
    deps = deps_with(CitationRepo())
    result = await agent.run('news?', deps=deps)
    assert result.output == 'NVDA beat [1]. Bogus.'
    assert [s['url'] for s in deps.citations.referenced] == ['https://news.example/nvda']
    tool_returns = [
        p.content for m in result.all_messages() for p in m.parts if p.part_kind == 'tool-return'
    ]
    assert any('Citation ids for these results' in str(c) for c in tool_returns)


async def test_output_hook_cleans_answer_and_records_sources():
    repo = CitationRepo()
    repo.register('A', 'https://x.com/a')
    agent = Agent(
        TestModel(custom_output_text='NVDA fell 3% [1]. Rates held [9].'),
        name='t',
        deps_type=AdvisorDeps,
        capabilities=[CitationsCapability()],
    )
    deps = deps_with(repo)
    result = await agent.run('what moved?', deps=deps)
    assert result.output == 'NVDA fell 3% [1]. Rates held.'
    assert [s['id'] for s in deps.citations.referenced] == [1]
