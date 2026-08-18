import pytest


@pytest.fixture(autouse=True)
def placeholder_exa_key(monkeypatch):
    """The Exa client needs a key string to construct, and a real key exported
    in the developer's shell must never let a test reach the live API. The
    'test' model only calls get_portfolio, so this placeholder is never sent."""
    monkeypatch.setenv('EXA_API_KEY', 'test-suite-placeholder')
