import pytest
import yaml
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from advisor.agents import ADVISOR_SPEC_PATH, CAPABILITY_TYPES
from advisor.agents.capabilities.core import AdvisorDeps, Portfolio


def advisor_agent(model: TestModel) -> Agent[AdvisorDeps, str]:
    return Agent.from_file(
        ADVISOR_SPEC_PATH,
        deps_type=AdvisorDeps,
        custom_capability_types=CAPABILITY_TYPES,
        model=model,
    )


def test_default_spec_loads():
    assert advisor_agent(TestModel()).name == 'advisor'


def test_unknown_capability_rejected(tmp_path):
    bad = tmp_path / 'bad.yaml'
    bad.write_text('name: x\ncapabilities:\n  - nope\n')
    with pytest.raises(ValueError, match='nope'):
        Agent.from_file(
            bad, deps_type=AdvisorDeps, custom_capability_types=CAPABILITY_TYPES, model=TestModel()
        )


async def test_spec_wires_tools_and_instructions():
    model = TestModel(call_tools=[])
    agent = advisor_agent(model)
    portfolio = Portfolio(as_of='2026-08-01', cash=100, currency='USD', positions=[])
    await agent.run('hi', deps=AdvisorDeps(portfolio=portfolio))
    params = model.last_model_request_parameters
    assert params is not None
    assert {t.name for t in params.function_tools} == {'get_portfolio', 'web_search', 'get_page'}


def test_capability_types_cover_spec():
    from pydantic_ai.capabilities import CAPABILITY_TYPES as BUILTIN_TYPES

    spec_names = set(yaml.safe_load(ADVISOR_SPEC_PATH.read_text())['capabilities'])
    known = {
        c if isinstance(c, str) else c.get_serialization_name()
        for c in (*CAPABILITY_TYPES, *BUILTIN_TYPES)
    }
    assert spec_names <= known
