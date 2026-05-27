"""
AgentGuard-X triage service entry point.

Runs on port 8001 so it does not conflict with FinanceFlow (:8000).

SECURITY: defaults to 127.0.0.1 (localhost-only).
  - Development / bare-metal:  HOST is unset → 127.0.0.1
  - Inside Docker container:   set HOST=0.0.0.0 via environment so the
    container's internal interface is reachable through the Docker network,
    while the Compose ports: mapping (127.0.0.1:8001:8001) controls what
    is exposed on the host.
"""
import os
import sys

# Ensure the AgentGuard-X root is on the path regardless of where this
# script is invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__":
    # FIX: default to 127.0.0.1 — never bind to 0.0.0.0 unless explicitly
    # set via HOST env var (e.g. inside a Docker container)
    _host = os.getenv("HOST", "127.0.0.1")
    _port = int(os.getenv("PORT", "8001"))
    _reload = os.getenv("ENV", "production") == "development"

    uvicorn.run(
        "triage.main:app",
        host=_host,
        port=_port,
        reload=_reload,
        log_level="info",
    )
