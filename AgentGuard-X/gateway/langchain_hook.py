import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, Union

import requests
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.callbacks import BaseCallbackHandler

from config import TRIAGE_SERVICE_URL, TRIAGE_ENDPOINT
from sanitizer.output_sanitizer import sanitize

logger = logging.getLogger(__name__)

# ANSI color codes
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
DIVIDER = "━" * 53


class ToolBlockedException(Exception):
    """Raised when AgentGuard-X blocks a tool invocation."""


def _color(decision: str) -> str:
    if decision == "FAST_PATH":
        return GREEN
    if decision == "SANDBOX":
        return YELLOW
    return RED


def _decision_icon(decision: str, instant_kill: bool) -> str:
    if decision == "BLOCK":
        return "🚫"
    if decision == "SANDBOX":
        return "🔶"
    return "✅"


def _print_decision_block(response_data: dict, processing_time_ms: float) -> None:
    decision = response_data.get("routing_decision", "UNKNOWN")
    instant_kill = response_data.get("instant_kill", False)
    color = _color(decision)
    icon = _decision_icon(decision, instant_kill)
    stage_results = response_data.get("stage_results", [])

    print(f"\n{DIM}{DIVIDER}{RESET}")
    print(f"{BOLD}{CYAN}[AgentGuard-X] REQUEST INTERCEPTED{RESET}")
    print(f"  {BOLD}Agent    :{RESET} {response_data.get('agent_id', '?')}")
    print(f"  {BOLD}Tool     :{RESET} {response_data.get('tool_name', '?')}")
    print(f"  {DIM}{'─' * 45}{RESET}")

    stage_labels = {1: "Stage 1", 2: "Stage 2", 3: "Stage 3", 4: "Stage 4", 5: "Stage 5"}
    for sr in stage_results:
        stage_num = sr.get("stage", 0)
        score = sr.get("score", 0.0)
        triggered = sr.get("triggered", False)
        reason = sr.get("reason", "")[:60]
        skipped = sr.get("details", {}).get("skipped", False)

        if skipped:
            status_str = f"⏭  SKIP "
            status_color = DIM
        elif stage_num == 2 and triggered and sr.get("details", {}).get("instant_kill"):
            status_str = f"❌ KILL "
            status_color = RED
        elif triggered:
            status_str = f"⚠  WARN "
            status_color = YELLOW
        else:
            status_str = f"✅ PASS "
            status_color = GREEN

        label = stage_labels.get(stage_num, f"Stage {stage_num}")
        print(f"  {status_color}{label}  : {status_str}({score:.2f}) — {reason}{RESET}")

    print(f"  {DIM}{'─' * 45}{RESET}")
    final_score = response_data.get("final_score", 0.0)
    kill_tag = " (INSTANT KILL)" if instant_kill else ""
    print(f"  {BOLD}Score    :{RESET} {color}{final_score:.2f}{RESET}  |  {BOLD}Decision:{RESET} {color}{icon} {decision}{kill_tag}{RESET}")
    print(f"  {BOLD}Time     :{RESET} {processing_time_ms:.1f}ms")

    owasp = response_data.get("owasp_category")
    if owasp:
        print(f"  {BOLD}OWASP    :{RESET} {owasp}")

    explanation = response_data.get("explanation", "")
    if explanation:
        print(f"  {DIM}{'─' * 45}{RESET}")
        # Word-wrap explanation at 50 chars
        words = explanation.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 55:
                print(line)
                line = "  " + word + " "
            else:
                line += word + " "
        if line.strip():
            print(line)

    print(f"{DIM}{DIVIDER}{RESET}\n")


class AgentGuardCallback(BaseCallbackHandler):

    def __init__(self, agent_id: str, agent_role: str, session_id: str):
        super().__init__()
        self.agent_id = agent_id
        self.agent_role = agent_role
        self.session_id = session_id

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        request_id = str(uuid.uuid4())

        try:
            tool_input = json.loads(input_str) if isinstance(input_str, str) else input_str
        except Exception:
            tool_input = {"raw": str(input_str)}

        payload = {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "tool_name": tool_name,
            "tool_input": tool_input if isinstance(tool_input, dict) else {"raw": str(tool_input)},
            "tool_input_raw": str(input_str),
            "agent_role": self.agent_role,
            "timestamp": time.time(),
            "request_id": request_id,
        }

        start = time.time()
        try:
            resp = requests.post(
                TRIAGE_SERVICE_URL + TRIAGE_ENDPOINT,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            response_data = resp.json()
        except requests.exceptions.ConnectionError:
            logger.error("Triage service unreachable — blocking tool execution (fail-closed)")
            raise ToolBlockedException(
                "AgentGuard-X triage service unreachable. Request blocked by default (fail-closed policy)."
            )
        except Exception as e:
            logger.error("Triage call failed: %s — blocking (fail-closed)", e)
            raise ToolBlockedException(
                f"AgentGuard-X triage call failed: {e}. Request blocked by default."
            )

        elapsed = (time.time() - start) * 1000
        _print_decision_block(response_data, elapsed)

        decision = response_data.get("routing_decision", "BLOCK")

        if decision == "BLOCK":
            explanation = response_data.get("explanation", "Request blocked by AgentGuard-X.")
            raise ToolBlockedException(f"[AgentGuard-X BLOCK] {explanation}")

        if decision == "SANDBOX":
            try:
                from sandbox import docker_runner
                from review import queue as review_queue
                from triage.models import TriageResponse

                sandbox_verdict = docker_runner.execute_in_sandbox(tool_name, payload["tool_input"])
                print(f"{YELLOW}[AgentGuard-X] Sandbox verdict: {sandbox_verdict.verdict}{RESET}")
                print(f"  Reason: {sandbox_verdict.reason}")
                print(f"  Execution: {sandbox_verdict.execution_ms:.1f}ms")

                # Enqueue for human review regardless
                try:
                    tr = TriageResponse(**response_data)
                    review_queue.enqueue(tr)
                    print(f"  {DIM}Request enqueued for human review.{RESET}")
                except Exception as eq_err:
                    logger.warning("Failed to enqueue for review: %s", eq_err)

                if sandbox_verdict.verdict == "KILL":
                    raise ToolBlockedException(
                        f"[AgentGuard-X SANDBOX KILL] {sandbox_verdict.reason}"
                    )
                # PROMOTE — allow tool to proceed
            except ToolBlockedException:
                raise
            except Exception as e:
                logger.error("Sandbox execution error: %s — blocking (fail-closed)", e)
                raise ToolBlockedException(f"Sandbox execution failed: {e}. Request blocked.")

        # FAST_PATH or SANDBOX PROMOTE — tool proceeds normally
        logger.info(
            "[AgentGuard-X] %s | score: %.2f | tool: %s | %.1fms",
            decision, response_data.get("final_score", 0.0), tool_name, elapsed,
        )

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        output_str = str(output)
        result = sanitize(output_str)

        if result.injection_detected:
            logger.warning(
                "[AgentGuard-X] INDIRECT INJECTION DETECTED in tool output! Patterns: %s",
                result.injection_patterns,
            )
            print(f"{RED}[AgentGuard-X] ⚠️  INDIRECT INJECTION in tool output: {result.injection_patterns}{RESET}")

        if result.pii_detected:
            high_conf = [e for e in result.pii_entities if e["score"] >= 0.85]
            if high_conf:
                logger.warning(
                    "[AgentGuard-X] PII detected in tool output: %s",
                    [e["entity_type"] for e in high_conf],
                )
                print(f"{YELLOW}[AgentGuard-X] ⚠️  PII in tool output: {[e['entity_type'] for e in high_conf]}{RESET}")

    def on_tool_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any) -> None:
        logger.error("[AgentGuard-X] Tool error: %s", error)
