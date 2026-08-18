# advisor-lite

A demo portfolio-counseling agent. Built small on purpose to show how I build, derived from a personal project. Not really meant to be used as-is (integrating with a broker is quite required to reach a reasonable UX), but functional.

You chat with an investment counselor about a seeded demo portfolio, editable in place from the web view. The agent reads the current holdings, searches the web when a question needs current information, and answers with inline citations you can follow to the source. Conversations are persistent and multiturn.

![demo](docs/demo.gif)
<!-- re-record: bin/record-demo.sh against a running stack with real keys -->

## Quickstart (60 seconds)

```bash
git clone https://github.com/quen-de/advisor-lite && cd advisor-lite
cp .env.example .env   # set MODEL, its provider key, and EXA_API_KEY
docker compose up --build
```

Open http://localhost:8080. No keys handy? `MODEL=test` runs a fake model, the same one CI uses.

## What this demonstrates

- **Agent-as-config**: the agent is a YAML spec ([`advisor.yaml`](api/src/advisor/agents/advisor.yaml)) loaded with pydantic-ai's `Agent.from_file`.
- **Native capabilities**: web research is pydantic-ai-harness's `ExaSearch`; portfolio and citations are `AbstractCapability` subclasses bundling instructions, tools, and hooks.
- **A citation pipeline**: search results register sources under friendly ids, the model cites with `[n]` markers, and an output processor strips orphan markers and returns only the sources actually referenced.
- **Multiturn persistence**: model message history is stored per conversation in Postgres and replayed on the next turn.
- **Provider-agnostic model choice**: one `MODEL` env var holding a pydantic-ai `provider:model` string. Missing provider keys fail fast with the exact variable name.
- **Keyless CI**: `MODEL=test` wires pydantic-ai's `TestModel` through the whole app, so lint, types, unit tests, and a full-stack compose smoke test run without secrets.
- **CI-run agent evals**: a [pydantic-evals](https://ai.pydantic.dev/evals/) dataset scores citation discipline, portfolio grounding, and refusal of out-of-scope requests against a real model, gated on a repo secret.
- **Deliberate containers**: three services with healthcheck-chained startup, non-root multi-stage images, and `docker compose watch` for development.

## Architecture

```mermaid
flowchart LR
    B[Browser SPA] --> N[nginx]
    N -->|/api| F[FastAPI]
    F --> S[chat service]
    S --> A[agent + capabilities]
    A -->|web_search| T[Exa]
    S --> P[(Postgres)]
```

Three backend layers with an enforced import boundary: `agents` (capabilities, spec, no I/O beyond tools), `service` (orchestration, persistence), `web` (FastAPI, SSE). Details in [docs/architecture.md](docs/architecture.md).

## Non-goals

Stated proudly: no auth, no real broker, no order execution, no migrations framework, demo data only. Nothing here is financial advice, and the UI says so on every screen.

## Development

```bash
# backend (from api/): tests need a local Postgres for the db-backed suite.
# The suite truncates tables, so it runs on its own database (created on first use);
# it refuses any TEST_DATABASE_URL whose database name does not end in _test.
docker compose up db -d
TEST_DATABASE_URL=postgresql://advisor:advisor@localhost:5432/advisor_test uv run pytest
uv run ruff check && uv run ty check

# frontend (from web/)
npm run test        # vitest
npm run e2e         # playwright against a mocked API
npm run lint && npm run typecheck

# whole stack with hot reload
docker compose watch

# evals against a real model (from api/); dataset and runner live in evals/
MODEL=anthropic:claude-sonnet-4-6 uv run python -m evals.run
```

Regenerate the typed API client: `uv run python scripts/export_openapi.py` (from `api/`) then `npm run generate-client` (from `web/`).

MIT licensed.
