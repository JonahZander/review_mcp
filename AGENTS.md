# Contributor commands

Run commands from the indicated package directory. Python 3.12 and uv 0.11.3 are used in CI.

## `google_reviews`

```sh
cd google_reviews
uv sync --locked --extra dev
uv run --locked --extra dev pytest tests/unit
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy .
```

Integration tests call paid external APIs and require explicitly configured credentials:

```sh
uv run --locked --extra dev pytest tests/integration
```

## `mcp_server`

```sh
cd mcp_server
uv sync --locked --extra dev
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy .
```

## Container checks

```sh
docker compose config --quiet
docker compose build
uv run --project mcp_server --locked --extra dev python scripts/smoke_server.py
```

The smoke test starts PostgreSQL through Compose and uses placeholder provider credentials. It does not call a paid provider API.
