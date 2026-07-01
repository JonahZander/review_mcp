FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the project's two source packages into /workspace.
# google_reviews/ is the business logic library; mcp_server/ is the FastMCP shim
# that wraps it. They are the entire codebase - the build context is the repo
# root (docker-compose sets context: .) so these two COPYs pull in the full app.
COPY google_reviews/ /workspace/google_reviews/
COPY mcp_server/ /workspace/mcp_server/

WORKDIR /workspace/mcp_server

# Install MCP server dependencies (fastmcp, uvicorn) into the venv.
# google_reviews is NOT installed - it is importable via PYTHONPATH below.
RUN uv sync --frozen --no-dev

# Make google_reviews importable as a sibling package
ENV PYTHONPATH=/workspace

EXPOSE 8002

CMD ["uv", "run", "python", "server.py"]
