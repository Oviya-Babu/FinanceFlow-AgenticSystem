"""
Bridge module that imports AgentGuard-X into the FinanceFlow runtime.

Adds AgentGuard-X to sys.path using a relative path so neither package
needs to know the other's install location. If AgentGuard-X is absent
(e.g. in tests), AGENTGUARD_ENABLED is False and a no-op stub is used,
so FinanceFlow continues to function without the security layer.
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

# FinanceFlow-AgenticSystem/
#   financeflow/app/security/  ← __file__
#   AgentGuard-X/
_AGENTGUARD_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "AgentGuard-X")
)
if _AGENTGUARD_PATH not in sys.path:
    sys.path.insert(0, _AGENTGUARD_PATH)

try:
    from gateway.langchain_hook import AgentGuardCallback, ToolBlockedException  # noqa: F401
    AGENTGUARD_ENABLED = True
    logger.info("AgentGuard-X loaded from %s", _AGENTGUARD_PATH)
except ImportError as _e:
    AGENTGUARD_ENABLED = False
    logger.warning("AgentGuard-X not available (%s) — security layer disabled", _e)

    class ToolBlockedException(Exception):  # type: ignore[no-redef]
        """Stub used when AgentGuard-X is not installed."""

    AgentGuardCallback = None  # type: ignore[assignment,misc]
