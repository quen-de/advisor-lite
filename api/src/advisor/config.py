import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic_ai.models.test import TestModel


class ConfigError(Exception):
    pass


# Env vars each mainstream provider's pydantic-ai client reads implicitly.
# Outer tuple: every group must be satisfied. Inner tuple: any one var satisfies the group.
PROVIDER_REQUIRED_VARS: dict[str, tuple[tuple[str, ...], ...]] = {
    'anthropic': (('ANTHROPIC_API_KEY',),),
    'openai': (('OPENAI_API_KEY',),),
    'azure': (('AZURE_OPENAI_ENDPOINT',), ('AZURE_OPENAI_API_KEY',)),
    'google': (('GOOGLE_API_KEY', 'GEMINI_API_KEY'),),
    'groq': (('GROQ_API_KEY',),),
    'mistral': (('MISTRAL_API_KEY',),),
    'deepseek': (('DEEPSEEK_API_KEY',),),
    'ollama': (('OLLAMA_BASE_URL',),),
}


@dataclass(frozen=True)
class Settings:
    model: str
    database_url: str
    portfolio_path: Path

    @classmethod
    def from_env(cls) -> 'Settings':
        model = os.environ.get('MODEL', '').strip()
        if not model:
            raise ConfigError(
                "MODEL is not set. Use a pydantic-ai 'provider:model' string, "
                'e.g. MODEL=anthropic:claude-sonnet-4-6, or MODEL=test for the fake model.'
            )
        provider = model.partition(':')[0]
        missing = [
            ' or '.join(group)
            for group in PROVIDER_REQUIRED_VARS.get(provider, ())
            if not any(os.environ.get(var) for var in group)
        ]
        if missing:
            raise ConfigError(
                f'MODEL={model} needs {", ".join(missing)} to be set. '
                f'The {provider} client reads them implicitly.'
            )
        return cls(
            model=model,
            database_url=os.environ.get('DATABASE_URL', ''),
            portfolio_path=Path(os.environ.get('PORTFOLIO_PATH', 'etc/portfolio.yaml')),
        )


def resolve_model(
    settings: Settings, test_call_tools: list[str] | Literal['all'] = 'all'
) -> str | TestModel:
    """Return the model pydantic-ai should run: TestModel for 'test', else the string.

    The 'test' seam keeps the whole app keyless: the Exa client still needs a
    key string to construct, so one is placed if absent, and callers building
    an agent with network tools pass `test_call_tools` to keep the fake model
    off them.
    """
    if settings.model == 'test':
        if not os.environ.get('EXA_API_KEY'):  # compose passes '' when unset
            os.environ['EXA_API_KEY'] = 'test-model-placeholder'
        return TestModel(call_tools=test_call_tools)
    return settings.model
