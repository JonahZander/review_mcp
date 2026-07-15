# mcp_server

FastMCP server exposing `google_reviews` tools via the MCP StreamableHTTP transport.

## Overview

```
MCP Client (Cursor, Claude, etc.)
    │
    └── local: http://localhost:8002/api/mcp/reviews
```

The server wraps `CompanyReviewService` from the sibling `google_reviews/` module as six MCP tools.
It owns no business logic - every tool is a direct pass-through to the service layer.

## Tools

| Tool                       | Output   | Description                                        |
|----------------------------|----------|----------------------------------------------------|
| `search_company_places`    | markdown | Discover Google Maps places for a company URL      |
| `search_company_places_raw`| JSON     | Same, structured output                            |
| `get_place_reviews`        | markdown | Reviews for one place by `data_id`                 |
| `get_place_reviews_raw`    | JSON     | Same, structured output                            |
| `get_company_overview`     | markdown | Bounded overview across locations and sort orders  |
| `get_company_overview_raw` | JSON     | Same, structured output                            |

### Parameter reference

| Parameter             | Used by              | Type         | Default          | Constraints                                      |
|-----------------------|----------------------|--------------|------------------|--------------------------------------------------|
| `company_url`         | all tools            | `str`        | required         | max 2048 chars                                   |
| `company_name`        | search, overview     | `str \| null`| `null`           | max 256 chars                                    |
| `data_id`             | place review tools   | `str`        | required         | max 256 chars                                    |
| `num_reviews`         | place review tools   | `int`        | `20`             | min 1                                            |
| `sort_order`          | place review tools   | `str \| null`| `most_relevant`  | `best`, `worst`, `newest`, `most_relevant`       |
| `max_companies`       | overview tools       | `int`        | `3`              | min 1                                            |
| `max_reviews_per_sort`| overview tools       | `int`        | `20`             | min 1, max 48                                    |

## Running in Docker

```bash
docker compose up mcp-server
```

- MCP endpoint: `http://localhost:8002/api/mcp/reviews`
- Env config: inherited from the repo-root `.env` (see `.env.example`), with `POSTGRES_DSN` overridden in `docker-compose.yml` to use the Docker-internal `postgres` hostname instead of `localhost`

To test tools interactively:

```bash
npx @modelcontextprotocol/inspector
```

Open the printed URL in a browser, set transport to `Streamable HTTP`, URL to `http://localhost:8002/api/mcp/reviews`, and connect.

## Running Locally (without Docker)

```bash
cd mcp_server
PYTHONPATH=.. uv run python server.py
```

Requires the repo-root `.env` to be reachable by `pydantic-settings`, which reads from the current working directory. The simplest setup: symlink it into this folder with `ln -s ../.env .env` so `python server.py` sees it. Set `POSTGRES_DSN` to point at a reachable PostgreSQL instance (e.g. `localhost:5432` with the postgres container's port mapped).

## Folder Structure

```
mcp_server/
  server.py              # FastMCP app + entrypoint
  tools/
    __init__.py
    reviews.py           # 6 MCP tool wrappers for CompanyReviewService
  pyproject.toml
  uv.lock
  Dockerfile
  .env.example
  README.md              # this file
```

## Design Choices

### PYTHONPATH instead of installable package

`google_reviews/` has `[tool.uv] package = false` - it is not built as an installable Python package. Rather than changing this, `mcp_server` adds `google_reviews/` to `PYTHONPATH` (`ENV PYTHONPATH=/workspace` in the Dockerfile, `PYTHONPATH=..` for local dev). This means:

- Changes to `google_reviews/` source are picked up with a container **restart**, not a full rebuild.
- `google_reviews`'s runtime dependencies (`requests`, `psycopg`, `pydantic`, etc.) are listed explicitly in `mcp_server/pyproject.toml` since they are not pulled in automatically.

### Stateless HTTP

`stateless_http=True` is passed to `mcp.run()`. Each MCP tool call is fully independent - the service handles its own DB-backed caching, so no MCP session state is needed. This also makes the server safe to run behind a load balancer with multiple replicas.

### Service initialised eagerly at startup

`create_review_service_from_settings()` is called inside `register()` at import time (server startup), not lazily on first tool call. This means misconfigured env vars (bad DSN, missing API key) cause a loud failure at startup rather than a silent failure mid-request.

### FastMCP transport string

The correct transport identifier for StreamableHTTP in FastMCP 2.x is `"streamable-http"`, not `"http"`. These are distinct values - using `"http"` would silently select a different transport.

### No health check endpoint

FastMCP's HTTP transport only exposes the `/api/mcp/reviews` endpoint. A `/health` route is not included to avoid adding Starlette middleware complexity for a non-critical feature. Use Docker's `depends_on: condition: service_healthy` on dependent services if a health check is needed in future.
