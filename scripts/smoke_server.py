"""Start the MCP server and verify that it listens without calling a provider API."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    process = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=repo_root / "mcp_server",
        env=env,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return process.returncode or 1
            try:
                with socket.create_connection(("127.0.0.1", 8002), timeout=0.5):
                    return 0
            except OSError:
                time.sleep(0.25)
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
