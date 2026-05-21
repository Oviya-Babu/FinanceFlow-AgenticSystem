"""
AgentGuard-X triage service entry point.

Runs on port 8001 so it does not conflict with FinanceFlow (:8000).
"""
import os
import sys

# Ensure the AgentGuard-X root is on the path regardless of where this
# script is invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "triage.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
