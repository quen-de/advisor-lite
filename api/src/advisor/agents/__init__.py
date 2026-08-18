from pathlib import Path

from pydantic_ai_harness.exa import ExaSearch

from advisor.agents.capabilities.citations import CitationsCapability
from advisor.agents.capabilities.portfolio import PortfolioCapability

ADVISOR_SPEC_PATH = Path(__file__).parent / 'advisor.yaml'

CAPABILITY_TYPES = (PortfolioCapability, ExaSearch, CitationsCapability)
