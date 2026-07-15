# Google Reviews MCP Server

<p align="center">
  <img src="blog/hero.png" alt="AI agent pulling Google Reviews across multiple locations" width="720" />
</p>

A purpose-built [Model Context Protocol](https://modelcontextprotocol.io) server that lets an AI agent sample Google Reviews for a company in **one tool call** - across a bounded set of locations, sorted by best / worst / newest / most-relevant, and cached in PostgreSQL so the same question isn't billed twice.

> **Companion essay:** [`blog/post.md`](./blog/post.md) - *Building the bridges your AI needs.* Explains what an MCP server is, what this one does, and the engineering tradeoffs behind it.

---

## Why this exists

SerpAPI already ships a generic MCP server. An agent could use that and do the whole job itself: search for places, choose locations, call "get reviews" once for best, again for worst, again for newest, and paginate as needed. It works - but every one of those steps is another agent turn, another round of reasoning, more tokens, and another billed API call.

**One test run, measured in 2026:** pulling an overview for Madrona Bakery took **2 MCP tool calls** (one to find the place, one for the overview) and about twelve seconds. Inside the server, that fanned out to **11 SerpAPI requests** - one search that tried three query variants, then four sort orders × two pages each. An equivalent low-level workflow would have required roughly 11 agent-directed steps. This is an example from one run, not a latency or turn-count guarantee.

When a workflow is predictable enough to describe in a sentence, the agent shouldn't have to rediscover it every time.

## Architecture

```
MCP Client (Claude, Cursor, Claude Code, ...)
    │  streamable-http
    ▼
mcp_server/           FastMCP wrapper - six tool definitions, zero business logic
    │  Python import  (PYTHONPATH=/workspace)
    ▼
google_reviews/       Orchestration: provider abstraction, retry, sort-order fan-out,
    │                                  storage, query-fallback search
    ├─▶ SerpAPI / SearchAPI   swap via SEARCH_PROVIDER env var
    └─▶ PostgreSQL            versioned snapshots, normalized by company URL
```

- **[`mcp_server/`](./mcp_server/README.md)** - the thin FastMCP shim. Six tools, each a direct pass-through to the service layer. No business logic.
- **[`google_reviews/`](./google_reviews/)** - the substance. Provider-agnostic orchestration, tenacity-based retry/backoff, Pydantic models, PostgreSQL repository with versioned scrape runs. Layered so a SearchAPI/SerpAPI swap is a config change, not a rewrite.
- **PostgreSQL** - every scrape is stored as a snapshot keyed by company website domain. Repeat queries hit the cache, not the paid API. Note: cached data has no TTL - it is reused until refreshed manually.

## Tools exposed

| Tool                        | Output   | What it does                                        |
|-----------------------------|----------|-----------------------------------------------------|
| `search_company_places`     | markdown | Discover Google Maps places for a company URL      |
| `search_company_places_raw` | JSON     | Same, structured output                             |
| `get_place_reviews`         | markdown | N reviews for one place in one sort order           |
| `get_place_reviews_raw`     | JSON     | Same, structured output                             |
| `get_company_overview`      | markdown | Bounded overview across locations × all sorts       |
| `get_company_overview_raw`  | JSON     | Same, structured output                             |

Full parameter reference and constraints in [`mcp_server/README.md`](./mcp_server/README.md).

## Quick start - Docker

```bash
cp .env.example .env
# Edit .env - set SERPAPI_API_KEY (free tier: 100 searches/month)
docker compose up --build
```

Compose binds both services to the local loopback interface. The example database password and API-key placeholders are local setup defaults; replace the provider key in `.env` before use.

- MCP endpoint: `http://localhost:8002/api/mcp/reviews`
- PostgreSQL: `localhost:5432` (db `reviews`, user `postgres`, password `postgres`)

**Try it** with the official MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

Point it at `http://localhost:8002/api/mcp/reviews` with transport **Streamable HTTP**. You'll see six tools. Start with `search_company_places` for any company URL you have.

## Quick start - without Docker

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and a reachable PostgreSQL instance.

```bash
cp .env.example .env                                # then edit: point POSTGRES_DSN at your local postgres
cd mcp_server
ln -s ../.env .env                                  # so pydantic-settings finds it from this CWD
PYTHONPATH=.. uv run python server.py
```

`google_reviews/` is imported as a sibling package via `PYTHONPATH=..` - it is not an installable package. `mcp_server/pyproject.toml` lists its runtime deps explicitly for this reason.

## Testing

```bash
cd google_reviews
uv run --extra dev pytest tests/unit           # 46 tests, fully mocked, no network, <1s
uv run --extra dev pytest tests/integration    # hits live APIs, needs valid keys
```

Integration tests are marked `@pytest.mark.integration` and `@pytest.mark.paid_api`, so you can select or skip them in CI depending on whether you want to burn API credits on every run.

Static checks:

```bash
cd mcp_server      && uv run --extra dev ruff check . && uv run --extra dev mypy .
cd google_reviews  && uv run --extra dev ruff check . && uv run --extra dev mypy .
```

## Local data and schema

The PostgreSQL cache has no automatic retention window; cached third-party review data remains in the local Docker volume until it is refreshed or the volume is removed. Schema setup currently uses idempotent `CREATE TABLE IF NOT EXISTS` statements rather than a migration framework. After an incompatible schema change, recreate the local database volume before starting the services again.

## Dependency audit notes

CI audits both locked runtime dependency sets. Three advisories are explicitly deferred: `PYSEC-2026-2475` and `PYSEC-2026-2476` require the separately tested FastMCP 3 migration, while transitive `diskcache` advisory `PYSEC-2026-2447` currently has no fixed release. The audit continues to fail for any other advisory.

## Project layout

```
.
├── README.md              - this file
├── LICENSE                - MIT
├── docker-compose.yml     - postgres + mcp-server
├── .env.example           - single-file config for both submodules
├── mcp_server/            - FastMCP shim (server.py + 6 tool wrappers)
├── google_reviews/        - business logic + 46 unit tests + live integration tests
└── blog/                  - "Building the bridges your AI needs" + hero art
```

## Further reading

- [`blog/post.md`](./blog/post.md) - the write-up for a non-engineering audience
- [`mcp_server/README.md`](./mcp_server/README.md) - tool reference, design choices (PYTHONPATH trick, stateless HTTP, etc.)

## License

MIT - see [`LICENSE`](./LICENSE).
