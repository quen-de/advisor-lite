from pathlib import Path

SRC = Path(__file__).parents[1] / 'src' / 'advisor'


def test_agents_and_service_never_import_web():
    for layer in ('agents', 'service'):
        for path in (SRC / layer).rglob('*.py'):
            assert 'advisor.web' not in path.read_text(), f'{path} imports advisor.web'
