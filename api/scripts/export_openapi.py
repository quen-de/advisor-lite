"""Export the OpenAPI schema to api/openapi.json for the typed client generator."""

import json
from pathlib import Path

from advisor.config import Settings
from advisor.web.app import create_app

REPO_ROOT = Path(__file__).parents[2]


def main() -> None:
    settings = Settings(
        model='test',
        database_url='',
        portfolio_path=REPO_ROOT / 'api' / 'etc' / 'portfolio.yaml',
    )
    schema = create_app(settings).openapi()
    out = REPO_ROOT / 'api' / 'openapi.json'
    out.write_text(json.dumps(schema, indent=2) + '\n')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
