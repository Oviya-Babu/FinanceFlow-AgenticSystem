"""
Bridge to the external sandbox_engine service.
Falls back gracefully to the local docker_runner when the service is unavailable.

The sandbox_engine runs on port 8003 and exposes POST /sandbox/evaluate.
"""
import logging
import time
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from triage.models import SandboxVerdict

logger = logging.getLogger(__name__)

SANDBOX_ENGINE_URL = os.getenv("SANDBOX_ENGINE_URL", "http://localhost:8003")


def evaluate_in_sandbox_engine(
    agent_id: str,
    agent_type: str,
    tool_name: str,
    tool_args: dict,
    triage_risk_score: float,
) -> dict:
    """
    Call the sandbox_engine microservice and return its result.
    Returns a dict with: verdict (ALLOW/BLOCK), risk_score, threats_detected, fingerprint.
    """
    import requests
    payload = {
        "agent_id":          agent_id,
        "agent_type":        agent_type,
        "tool_name":         tool_name,
        "tool_args":         tool_args,
        "triage_risk_score": triage_risk_score,
    }
    resp = requests.post(
        f"{SANDBOX_ENGINE_URL}/sandbox/evaluate",
        json=payload,
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()


def execute_sandbox(
    tool_name: str,
    tool_input: dict,
    agent_id: str = "unknown",
    agent_role: str = "unknown",
    risk_score: float = 0.5,
) -> SandboxVerdict:
    """
    Primary entry point: try sandbox_engine first, fall back to docker_runner.
    Returns SandboxVerdict with verdict=PROMOTE or KILL.
    """
    start = time.time()

    try:
        result = evaluate_in_sandbox_engine(
            agent_id=agent_id,
            agent_type=_role_to_type(agent_role),
            tool_name=tool_name,
            tool_args=tool_input,
            triage_risk_score=risk_score,
        )
        elapsed = (time.time() - start) * 1000

        sandbox_verdict = result.get("verdict", "BLOCK")
        verdict = "PROMOTE" if sandbox_verdict == "ALLOW" else "KILL"

        threats = result.get("threats_detected", [])
        baseline_violations = result.get("baseline_violations", [])
        fingerprint = result.get("fingerprint", {})

        all_issues = threats + baseline_violations
        reason = (
            f"Sandbox engine verdict: {sandbox_verdict}. "
            + (f"Threats: {', '.join(all_issues)}" if all_issues else "No threats detected.")
            + f" Runtime: {result.get('runtime_used', 'docker')}."
            + f" Execution: {result.get('execution_time_ms', 0):.1f}ms."
        )

        fingerprint["source"] = "sandbox_engine"
        fingerprint["sandbox_verdict"] = sandbox_verdict
        fingerprint["threats"] = threats
        fingerprint["baseline_violations"] = baseline_violations
        fingerprint["network_access"] = _check_network_from_fingerprint(fingerprint, threats)
        fingerprint["file_access"] = _check_file_from_fingerprint(fingerprint, threats)
        fingerprint["syscalls_analyzed"] = fingerprint.get("syscalls_analyzed", 0)

        return SandboxVerdict(
            verdict=verdict,
            fingerprint=fingerprint,
            reason=reason,
            execution_ms=round(elapsed, 2),
        )

    except Exception as e:
        logger.warning("sandbox_engine unavailable (%s), falling back to local docker_runner", e)
        from sandbox import docker_runner
        return docker_runner.execute_in_sandbox(tool_name, tool_input)


def _role_to_type(role: str) -> str:
    mapping = {
        "research_agent":     "ResearchAgent",
        "analyst_agent":      "AnalystAgent",
        "report_agent":       "ReportAgent",
        "orchestrator_agent": "ResearchAgent",
        "data_agent":         "ResearchAgent",
    }
    return mapping.get(role, "UnknownAgent")


def _check_network_from_fingerprint(fingerprint: dict, threats: list) -> list:
    network_calls = []
    if any("network" in t.lower() or "http" in t.lower() or "curl" in t.lower() for t in threats):
        network_calls.append("suspicious_domain_contacted")
    return network_calls


def _check_file_from_fingerprint(fingerprint: dict, threats: list) -> list:
    files = []
    if any("file" in t.lower() or "read" in t.lower() or "/etc" in t.lower() for t in threats):
        files.append("sensitive_file_accessed")
    return files
