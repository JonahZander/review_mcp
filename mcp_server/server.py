"""FastMCP server - exposes google_reviews tools via StreamableHTTP.

Run locally:  PYTHONPATH=.. uv run python server.py
Docker:       docker compose up mcp-server
Inspector UI: http://localhost:8002
MCP endpoint: http://localhost:8002/api/mcp/reviews
"""

from __future__ import annotations

import atexit
import logging

from fastmcp import FastMCP

from tools.reviews import register

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("review-mcp")
_service = register(mcp)
atexit.register(_service.close)

if __name__ == "__main__":
    logger.info("Starting review MCP server on :8002")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002, path="/api/mcp/reviews", stateless_http=True)
