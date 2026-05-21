import logging
import threading
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SANDBOX_IMAGE, SANDBOX_TIMEOUT_SECONDS, SANDBOX_MEMORY_LIMIT, SANDBOX_CPU_QUOTA
from triage.models import SandboxVerdict

logger = logging.getLogger(__name__)

# Safe simulation scripts per tool
_TOOL_SCRIPTS = {
    "read_file": """
import sys
# Simulate reading a dummy file
content = "Q3 Revenue: $2.4M. Key accounts: Acme Corp, TechFlow Inc."
print(f"[SANDBOX] read_file result: {content}")
""",
    "http_post": """
import socket
import sys

url = sys.argv[1] if len(sys.argv) > 1 else "unknown"
print(f"[SANDBOX] Attempting http_post to: {url}")
try:
    # Network is disabled — this will fail
    s = socket.create_connection(("8.8.8.8", 80), timeout=2)
    s.close()
    print("[SANDBOX] UNEXPECTED: network connection succeeded")
except Exception as e:
    print(f"[SANDBOX] Network blocked (expected): {e}")
print("[SANDBOX] http_post simulation complete")
""",
    "web_search": """
print("[SANDBOX] web_search simulation — no network access required")
print("[SANDBOX] Result: simulated search results returned safely")
""",
    "execute_shell": """
import sys
print("[SANDBOX] execute_shell intercepted in sandbox")
print("[SANDBOX] Command would have been executed — blocked by policy")
sys.exit(1)
""",
}

_DEFAULT_SCRIPT = """
print("[SANDBOX] Unknown tool — executing in safe no-op mode")
"""


def _pull_image_if_needed() -> None:
    try:
        import docker
        client = docker.from_env(timeout=30)
        try:
            client.images.get(SANDBOX_IMAGE)
            logger.info("Sandbox image '%s' already present.", SANDBOX_IMAGE)
        except docker.errors.ImageNotFound:
            logger.info("Pulling sandbox image '%s'...", SANDBOX_IMAGE)
            client.images.pull(SANDBOX_IMAGE)
            logger.info("Sandbox image pulled.")
    except Exception as e:
        logger.warning("Could not pre-pull sandbox image: %s", e)


def warmup() -> None:
    _pull_image_if_needed()


def execute_in_sandbox(tool_name: str, tool_input: dict) -> SandboxVerdict:
    start = time.time()
    script = _TOOL_SCRIPTS.get(tool_name, _DEFAULT_SCRIPT)
    input_str = str(tool_input.get("url", tool_input.get("query", tool_input.get("filepath", ""))))

    try:
        import docker
        client = docker.from_env(timeout=60)

        result_holder = {"output": None, "error": None}

        def _run():
            try:
                out = client.containers.run(
                    image=SANDBOX_IMAGE,
                    command=["python3", "-c", script, input_str],
                    mem_limit=SANDBOX_MEMORY_LIMIT,
                    cpu_quota=SANDBOX_CPU_QUOTA,
                    network_disabled=True,
                    read_only=False,
                    remove=True,
                    detach=False,
                    stdout=True,
                    stderr=True,
                )
                result_holder["output"] = out.decode("utf-8") if isinstance(out, bytes) else str(out)
            except Exception as ex:
                result_holder["error"] = ex

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=SANDBOX_TIMEOUT_SECONDS)

        if t.is_alive() or result_holder["error"] is not None:
            err = result_holder.get("error") or TimeoutError("Container timed out")
            raise err

        output = result_holder["output"] or ""
        elapsed = (time.time() - start) * 1000

        fingerprint = {
            "tool_name": tool_name,
            "exit_code": 0,
            "stdout": output[:500],
            "network_attempt": "Network blocked (expected)" in output or "socket" in output.lower(),
            "unexpected_network_success": "UNEXPECTED: network connection succeeded" in output,
            "execution_ms": round(elapsed, 2),
        }

        anomalous = (
            fingerprint["unexpected_network_success"]
            or (tool_name == "execute_shell")
            or "error" in output.lower()
        )

        if anomalous:
            verdict = "KILL"
            reason = _explain_kill(tool_name, fingerprint, output)
        else:
            verdict = "PROMOTE"
            reason = f"Tool '{tool_name}' behaved as expected in sandbox. No anomalous activity detected."

        return SandboxVerdict(
            verdict=verdict,
            fingerprint=fingerprint,
            reason=reason,
            execution_ms=round(elapsed, 2),
        )

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        logger.error("Docker sandbox execution failed: %s", e)

        is_network_attempt = _is_network_tool(tool_name)
        fingerprint = {
            "tool_name": tool_name,
            "exit_code": -1,
            "error": str(e),
            "network_attempt": is_network_attempt,
            "unexpected_network_success": False,
            "execution_ms": round(elapsed, 2),
        }

        if "network" in str(e).lower() or is_network_attempt:
            verdict = "KILL"
            reason = f"Network connection attempted from sandbox for tool '{tool_name}'. Blocked. Error: {e}"
        else:
            verdict = "KILL"
            reason = f"Docker daemon unreachable or container execution failed: {e}. Defaulting to KILL."

        return SandboxVerdict(
            verdict=verdict,
            fingerprint=fingerprint,
            reason=reason,
            execution_ms=round(elapsed, 2),
        )


def _is_network_tool(tool_name: str) -> bool:
    return tool_name in ("http_post", "web_search")


def _explain_kill(tool_name: str, fingerprint: dict, output: str) -> str:
    reasons = []
    if fingerprint.get("unexpected_network_success"):
        reasons.append("Unexpected network connection succeeded from sandbox")
    if tool_name == "execute_shell":
        reasons.append("execute_shell tool should never reach sandbox (policy violation)")
    if "error" in output.lower():
        reasons.append(f"Anomalous output detected in sandbox: {output[:100]}")
    return "; ".join(reasons) if reasons else f"Anomalous behavior from tool '{tool_name}' in sandbox."
