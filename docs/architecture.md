# Architecture

## Layers

The backend is one Python package, `advisor`, in three layers:

- `agents/`: the three capabilities and the YAML spec that assembles them into a pydantic-ai agent. No database, no HTTP framework.
- `service/`: chat orchestration and Postgres persistence. Streams agent output, stores exchanges.
- `web/`: FastAPI routes and SSE encoding. Thin; every decision lives below it.

The import boundary is one-way: `web` imports `service`, `service` imports `agents`, never the reverse. A test walks the source tree and fails on any `advisor.web` import from the lower layers.

## Capabilities

Each capability is a pydantic-ai `AbstractCapability[AdvisorDeps]` subclass contributing instructions and tools natively:

- `PortfolioCapability` (ours): the `get_portfolio` tool plus grounding instructions.
- `ExaSearch` (from pydantic-ai-harness): `web_search` and `get_page` tools backed by the Exa API, keyed by `EXA_API_KEY`.
- `Instrumentation` (pydantic-ai built-in): OTel spans for runs, model requests, and tool calls; live only when startup finds `LOGFIRE_API_KEY` and configures Logfire, a no-op otherwise.
- `CitationsCapability` (ours): citation instructions plus two hooks. `after_tool_execute` registers the sources any `ToolReturn` reports in `metadata['sources']` and appends their citation ids to the result the model sees; `after_output_process` strips orphan markers and records the referenced sources on the run's `CitationRepo`.

`advisor.yaml` is a native pydantic-ai agent spec loaded with `Agent.from_file`, passing `deps_type`, the capability types, and the runtime model at each call site. Capability names resolve via each class's serialization name; unknown names fail at load.

## The citation pipeline

1. Exa's tools report each result's url and title in `ToolReturn.metadata['sources']`; the citations capability registers them in a per-run `CitationRepo`, which dedupes by url and hands out sequential integer ids.
2. The capability appends a citation-id legend to every such tool result and instructs the model to mark web-derived claims with those ids.
3. The citations capability's output hook drops any `[n]` marker with no registered source, returns the cleaned text as the run output, and stores the referenced sources on the repo for the service to persist.

The repo is seeded from the chat's persisted citation state (every source registered on earlier turns), so ids are stable across the whole conversation: a follow-up answer can cite a source it only saw in the history, and the marker still resolves. After each run the updated state is written back with the exchange.

## SSE vocabulary

`POST /api/chats/{id}/messages` streams `text/event-stream`:

| event | data | meaning |
|---|---|---|
| `status` | `{"id": str, "text": str}` | a tool call started; parallel calls each announce with their own id. The client stacks the line into the current thinking bubble |
| `status_done` | `{"id": str}` | that tool call finished; the client marks its line with a check |
| `thought` | `{"text": str}` | next chunk of the model's thinking stream; the client streams it into the current bubble (a thought after a tool round opens the next bubble) |
| `delta` | `{"text": str}` | next chunk of text. All text belongs to the chat itself - commentary between tool rounds and the answer alike - so the client appends it to the current text segment |
| `title` | `{"chat_id": str, "title": str}` | first message's title; the titling task starts with the run, so this arrives as soon as it resolves - between other events or after `done`. The task survives disconnects |
| `sources` | `{"sources": [{id, title, url}], "text": str}` | referenced sources plus the processed answer text |
| `done` | `{"chat_id": str}` | exchange persisted |
| `error` | `{"message": str}` | run failed, nothing persisted |

The frontend, the compose smoke test, and the service tests all assert this table.

## The MODEL=test seam

`resolve_model` returns pydantic-ai's `TestModel` when `MODEL=test`, otherwise the `provider:model` string untouched. The Exa client needs a key string to construct, so the seam places a placeholder when none is set, and agent builders pass `test_call_tools=['get_portfolio']` so the fake model never dials out. Everything else downstream is identical, which is what lets CI exercise the full stack, including the compose smoke test, with no secrets.

## Persistence

Four tables. `chats` and `exchanges` hold conversations: each exchange stores the user text, the processed answer, the referenced sources, and the serialized pydantic-ai message batch for that run; the chat row carries the accumulated citation state that seeds the next run's `CitationRepo`. History for a chat is the concatenation of its batches, deserialized and passed as `message_history` to the next run.

The message batch also drives display persistence: on load, `display_parts` rebuilds each assistant message's transcript - thinking bubbles with their tool calls, commentary segments, the answer - from the stored batch, so a refresh shows what the live stream showed without storing any of it twice.

`portfolio` (single row: cash, currency, as_of) and `positions` hold the holdings. The yaml file seeds them once, on the first boot against an empty database; after that the database is canonical, the web view edits it, and every agent run reads the current state. Any edit moves `as_of` to today. Schema is one idempotent `schema.sql` applied at startup; a migrations framework would be ceremony at this size.
