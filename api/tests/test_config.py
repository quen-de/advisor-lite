import pytest

from advisor.config import ConfigError, Settings, resolve_model

BASE_ENV = {'MODEL': 'test', 'DATABASE_URL': 'postgresql://x/y'}

PROVIDER_VARS = (
    'ANTHROPIC_API_KEY',
    'OPENAI_API_KEY',
    'OPENAI_BASE_URL',
    'AZURE_OPENAI_ENDPOINT',
    'AZURE_OPENAI_API_KEY',
    'OPENAI_API_VERSION',
    'GOOGLE_API_KEY',
    'GEMINI_API_KEY',
    'GROQ_API_KEY',
    'MISTRAL_API_KEY',
    'DEEPSEEK_API_KEY',
    'OLLAMA_BASE_URL',
    'OLLAMA_API_KEY',
)


def set_env(monkeypatch, extra=None, remove=()):
    for key in ('MODEL', 'DATABASE_URL', 'TAVILY_API_KEY', 'PORTFOLIO_PATH', *PROVIDER_VARS):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**BASE_ENV, **(extra or {})}.items():
        if key not in remove:
            monkeypatch.setenv(key, value)


def test_model_required(monkeypatch):
    set_env(monkeypatch, remove=('MODEL',))
    with pytest.raises(ConfigError, match='MODEL'):
        Settings.from_env()


def test_known_provider_requires_key(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'anthropic:claude-sonnet-4-6'})
    with pytest.raises(ConfigError, match='ANTHROPIC_API_KEY'):
        Settings.from_env()


def test_known_provider_with_key_ok(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'openai:gpt-5.2', 'OPENAI_API_KEY': 'k'})
    assert Settings.from_env().model == 'openai:gpt-5.2'


def test_azure_requires_endpoint_and_key(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'azure:gpt-5.2'})
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env()
    assert 'AZURE_OPENAI_ENDPOINT' in str(excinfo.value)
    assert 'AZURE_OPENAI_API_KEY' in str(excinfo.value)


def test_azure_endpoint_alone_not_enough(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'azure:gpt-5.2', 'AZURE_OPENAI_ENDPOINT': 'https://e'})
    with pytest.raises(ConfigError, match='AZURE_OPENAI_API_KEY'):
        Settings.from_env()


def test_azure_with_endpoint_and_key_ok(monkeypatch):
    set_env(
        monkeypatch,
        extra={
            'MODEL': 'azure:gpt-5.2',
            'AZURE_OPENAI_ENDPOINT': 'https://e',
            'AZURE_OPENAI_API_KEY': 'k',
        },
    )
    assert Settings.from_env().model == 'azure:gpt-5.2'


def test_google_accepts_either_key_var(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'google:gemini-3-pro', 'GEMINI_API_KEY': 'k'})
    assert Settings.from_env().model == 'google:gemini-3-pro'
    set_env(monkeypatch, extra={'MODEL': 'google:gemini-3-pro'})
    with pytest.raises(ConfigError, match='GOOGLE_API_KEY or GEMINI_API_KEY'):
        Settings.from_env()


def test_ollama_requires_base_url(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'ollama:llama3.3'})
    with pytest.raises(ConfigError, match='OLLAMA_BASE_URL'):
        Settings.from_env()
    set_env(
        monkeypatch, extra={'MODEL': 'ollama:llama3.3', 'OLLAMA_BASE_URL': 'http://localhost:11434'}
    )
    assert Settings.from_env().model == 'ollama:llama3.3'


def test_deepseek_requires_key(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'deepseek:deepseek-v4-pro'})
    with pytest.raises(ConfigError, match='DEEPSEEK_API_KEY'):
        Settings.from_env()
    set_env(monkeypatch, extra={'MODEL': 'deepseek:deepseek-v4-pro', 'DEEPSEEK_API_KEY': 'k'})
    assert Settings.from_env().model == 'deepseek:deepseek-v4-pro'


def test_unknown_provider_passes_through(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'cerebras:zap'})
    assert Settings.from_env().model == 'cerebras:zap'


def test_test_model_needs_no_key(monkeypatch):
    set_env(monkeypatch)
    settings = Settings.from_env()
    from pydantic_ai.models.test import TestModel

    assert isinstance(resolve_model(settings), TestModel)


def test_real_model_resolves_to_string(monkeypatch):
    set_env(monkeypatch, extra={'MODEL': 'openai:gpt-5.2', 'OPENAI_API_KEY': 'k'})
    assert resolve_model(Settings.from_env()) == 'openai:gpt-5.2'
