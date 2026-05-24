"""
FinanceFlow autonomous task-graph orchestrator.

The orchestrator:
1. Classifies user intent.
2. Produces a real TaskGraph (ordered list of TaskNode objects — not a text blob).
3. Executes each node by calling AgentGuard-X first, then the tool based on verdict.
4. Maintains a reasoning chain surfaced to the user.
5. Hard-stops on BLOCK (or SANDBOX→KILL); never bypasses the mesh.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

import httpx

from financeflow.tool_registry import (
    AGENTGUARD_URL,
    TOOL_FN_MAP,
    check_with_guard,
    execute_tool_sync,
)

logger = logging.getLogger(__name__)

# ─── Domain models ────────────────────────────────────────────────────────────

class IntentType(str, Enum):
    FINANCIAL_RESEARCH  = "financial_research"
    GENERAL_ASSISTANT   = "general_assistant"
    DOCUMENT_GENERATION = "document_generation"
    COMPUTATION         = "computation"
    SECURITY_THREAT     = "security_threat"


# Canonical status vocabulary (spec §5 §1):
#   Security verdicts:  ALLOW | SANDBOX | BLOCK
#   Step execution:     pending | running | done | blocked | failed
#   Mapping: ALLOW/SANDBOX→PROMOTE → done | BLOCK/SANDBOX→KILL → blocked

@dataclass
class TaskNode:
    step_id:    str
    step_num:   int
    agent_id:   str
    agent_role: str
    tool_name:  str
    tool_input: dict
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    # execution state
    status:     str = "pending"        # pending|running|done|blocked|failed
    verdict:    Optional[str] = None   # ALLOW|SANDBOX|BLOCK
    risk_score: float = 0.0
    guard_detail: dict = field(default_factory=dict)
    output:     Optional[dict] = None
    reasoning:  str = ""
    error:      Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def duration_ms(self) -> float:
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at) * 1000, 1)
        return 0.0

    def to_dict(self) -> dict:
        return {
            "step_id":      self.step_id,
            "step_num":     self.step_num,
            "agent_id":     self.agent_id,
            "agent_role":   self.agent_role,
            "tool_name":    self.tool_name,
            "tool_input":   self.tool_input,
            "description":  self.description,
            "depends_on":   self.depends_on,
            "status":       self.status,
            "verdict":      self.verdict,
            "risk_score":   self.risk_score,
            "guard_detail": self.guard_detail,
            "output":       self.output,
            "reasoning":    self.reasoning,
            "error":        self.error,
            "started_at":   self.started_at,
            "completed_at": self.completed_at,
            "duration_ms":  self.duration_ms(),
        }


@dataclass
class TaskGraph:
    query:       str
    intent:      IntentType
    steps:       list[TaskNode]
    session_id:  str
    workflow_id: str
    created_at:  float
    reasoning_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query":          self.query,
            "intent":         self.intent.value,
            "workflow_id":    self.workflow_id,
            "session_id":     self.session_id,
            "created_at":     self.created_at,
            "steps":          [s.to_dict() for s in self.steps],
            "reasoning_chain": self.reasoning_chain,
        }


@dataclass
class ExecutionResult:
    workflow_id:   str
    status:        str  # completed | blocked | partial | failed
    graph:         TaskGraph
    outputs:       list[dict]
    artifacts:     list[str]
    security_events: list[dict]
    reasoning_chain: list[str]
    started_at:    float
    completed_at:  float
    total_ms:      float

    def to_dict(self) -> dict:
        return {
            "workflow_id":    self.workflow_id,
            "status":         self.status,
            "graph":          self.graph.to_dict(),
            "outputs":        self.outputs,
            "artifacts":      self.artifacts,
            "security_events": self.security_events,
            "reasoning_chain": self.reasoning_chain,
            "started_at":     self.started_at,
            "completed_at":   self.completed_at,
            "total_ms":       self.total_ms,
        }


# ─── Intent classification ────────────────────────────────────────────────────

_INTENT_PATTERNS = {
    IntentType.SECURITY_THREAT: [
        r"ignore\s+(previous|all|your)\s+instructions",
        r"override\s+system",
        r"disregard\s+(all|previous|your)",
        r"access\s+all\s+stored\s+api\s+keys",
        r"export\s+all\s+customer",
        r"execute\s+hidden\s+instructions",
        r"act\s+as\s+if\s+you\s+(have\s+no\s+restrictions|are\s+)",
    ],
    IntentType.FINANCIAL_RESEARCH: [
        r"\b(nvda|nvidia|tsla|tesla|aapl|apple|spy|s&p|nasdaq|dow)\b",
        r"\b(earnings|revenue|eps|market\s+cap|stock|financials|q[1-4]\s+\d{4})\b",
        r"\b(analysis|market\s+analysis|investment|portfolio|hedge\s+fund)\b",
        r"\b(generate|create|produce|write)\b.*(report|analysis)",
        r"\b(send|email).*(team|investment|analyst)",
    ],
    IntentType.DOCUMENT_GENERATION: [
        r"\b(write|create|generate|produce)\b.*(document|report|summary|brief)",
        r"\b(draft|compose|format)\b",
        r"\b(pdf|docx|markdown)\b",
    ],
    IntentType.COMPUTATION: [
        r"\bwhat\s+is\s+\d+\s*[\+\-\*/]\s*\d+\b",
        r"\bcalculate\b",
        r"\bpython\s+(function|code|script)\b",
        r"\brecursion\b|\balgorithm\b|\bsort\b",
    ],
}


def classify_intent(query: str) -> IntentType:
    q = query.lower()
    for intent, patterns in _INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q, re.IGNORECASE):
                return intent
    return IntentType.GENERAL_ASSISTANT


# ─── Task graph templates ─────────────────────────────────────────────────────

def _make_step(num: int, agent_id: str, role: str, tool: str,
               inp: dict, desc: str, depends: list[str] | None = None) -> TaskNode:
    return TaskNode(
        step_id=f"step-{num}",
        step_num=num,
        agent_id=agent_id,
        agent_role=role,
        tool_name=tool,
        tool_input=inp,
        description=desc,
        depends_on=depends or [],
    )


def build_task_graph(query: str, session_id: str, intent: IntentType,
                     uploaded_context: str = "", workflow_id: str | None = None) -> TaskGraph:
    """
    Create an ordered TaskGraph from the query and classified intent.
    Each node has an agent, tool, inputs, and declared dependencies.
    Per-workflow agent IDs prevent behavioral drift accumulation across queries.
    """
    wf_id = workflow_id or f"wf-{uuid.uuid4().hex[:10]}"
    # Short suffix for per-workflow agent IDs — isolates drift between requests
    wf_sfx = wf_id.split("-", 1)[-1][:8]
    r_agent  = f"research-{wf_sfx}"   # research_agent
    a_agent  = f"analyst-{wf_sfx}"    # analyst_agent
    rp_agent = f"report-{wf_sfx}"     # report_agent

    steps: list[TaskNode] = []
    reasoning: list[str] = []

    # ── Financial research + report + email (canonical NVIDIA scenario)
    if intent == IntentType.FINANCIAL_RESEARCH:
        reasoning.append("Intent: financial research. Building multi-step research → analysis → report → email pipeline.")

        # Extract ticker
        ticker_match = re.search(
            r"\b(NVDA|NVIDIA|TSLA|TESLA|AAPL|APPLE|SPY|MSFT|GOOGL|META|AMZN)\b",
            query, re.IGNORECASE
        )
        ticker = ticker_match.group(0).upper() if ticker_match else "NVDA"
        full_name = {"NVDA": "NVIDIA", "NVIDIA": "NVIDIA", "TSLA": "Tesla",
                     "TESLA": "Tesla", "AAPL": "Apple", "MSFT": "Microsoft",
                     "GOOGL": "Google", "META": "Meta", "AMZN": "Amazon"}.get(ticker, ticker)

        # Derive report title / quarter from query
        q_match = re.search(r"Q[1-4]\s+\d{4}", query, re.IGNORECASE)
        period = q_match.group(0) if q_match else "Q3 2024"

        reasoning.append(f"Identified company: {full_name} ({ticker}), period: {period}.")

        steps = [
            _make_step(1, r_agent, "research_agent", "financial_search",
                       {"query": f"{ticker} {period} earnings revenue EPS"},
                       f"Fetch {full_name} {period} financial data via Yahoo Finance"),
            _make_step(2, r_agent, "research_agent", "sec_filings",
                       {"company": full_name},
                       f"Retrieve {full_name} SEC filings (10-Q/10-K)",
                       depends=["step-1"]),
            _make_step(3, r_agent, "research_agent", "web_search",
                       {"query": f"{full_name} {period} market analysis analyst sentiment"},
                       f"Search for market analysis and analyst sentiment",
                       depends=["step-1"]),
            _make_step(4, a_agent, "analyst_agent", "query_internal_db",
                       {"query": f"SELECT metrics FROM financial_data WHERE ticker='{ticker}' AND period='{period}'"},
                       f"Query internal financial database for {ticker}",
                       depends=["step-1"]),
            _make_step(5, a_agent, "analyst_agent", "write_report",
                       {"title": f"{full_name} {period} Market Analysis Report",
                        "content": f"[auto-populated from steps 1-4 outputs]"},
                       f"Generate {full_name} {period} analysis report with PDF artifact",
                       depends=["step-1", "step-2", "step-3", "step-4"]),
            _make_step(6, rp_agent, "report_agent", "send_email",
                       {"to": "investment-team@financeflow.com",
                        "subject": f"{full_name} {period} Market Analysis Report",
                        "body": "[auto-populated from report]"},
                       "Send report to investment team",
                       depends=["step-5"]),
        ]
        reasoning.append("Plan: 6 steps — financial data → SEC filings → web research → DB query → PDF report → email delivery.")

    # ── General assistant (math, explanations, code)
    elif intent == IntentType.GENERAL_ASSISTANT:
        reasoning.append("Intent: general assistant query. Single-step LLM answer path.")
        context = uploaded_context or ""
        steps = [
            _make_step(1, r_agent, "research_agent", "llm_answer",
                       {"question": query, "context": context},
                       "Answer the question directly via language model"),
        ]

    # ── Computation
    elif intent == IntentType.COMPUTATION:
        reasoning.append("Intent: computation. Routing to LLM for explanation/answer.")
        steps = [
            _make_step(1, r_agent, "research_agent", "llm_answer",
                       {"question": query}, "Compute or explain the requested concept"),
        ]

    # ── Document generation
    elif intent == IntentType.DOCUMENT_GENERATION:
        reasoning.append("Intent: document generation. Research then produce artifact.")
        steps = [
            _make_step(1, r_agent, "research_agent", "web_search",
                       {"query": query}, "Research content for the document"),
            _make_step(2, a_agent, "analyst_agent", "write_report",
                       {"title": "Generated Document", "content": "[from step-1]"},
                       "Generate document with PDF artifact",
                       depends=["step-1"]),
        ]

    # ── Security threat — still passes through AgentGuard-X normally
    elif intent == IntentType.SECURITY_THREAT:
        reasoning.append("Intent: potentially malicious query. Routing through AgentGuard-X — the mesh will decide. Agent does not pre-judge.")
        steps = [
            _make_step(1, r_agent, "research_agent", "web_search",
                       {"query": query},
                       "Pass query through AgentGuard-X security mesh for verdict"),
        ]

    return TaskGraph(
        query=query,
        intent=intent,
        steps=steps,
        session_id=session_id,
        workflow_id=wf_id,
        created_at=time.time(),
        reasoning_chain=reasoning,
    )


# ─── Graph executor ───────────────────────────────────────────────────────────

EmitFn = Callable[[dict], Awaitable[None]]

_SANDBOX_URL = "http://localhost:8003/sandbox/evaluate"


async def _sandbox_evaluate(step: TaskNode) -> dict:
    """Route to sandbox_engine. Returns {"verdict": "ALLOW"|"BLOCK", ...}."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_SANDBOX_URL, json={
                "agent_id":   step.agent_id,
                "agent_type": step.agent_role,
                "tool_name":  step.tool_name,
                "tool_args":  step.tool_input,
                "triage_risk_score": step.risk_score,
            })
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning("Sandbox engine unreachable: %s — treating as BLOCK", exc)
    return {"verdict": "BLOCK", "reason": "sandbox_unavailable"}


async def _execute_step(
    step: TaskNode,
    step_outputs: dict[str, Any],
    emit: EmitFn,
    security_events: list[dict],
) -> bool:
    """
    Execute a single task node.
    1. Fill dynamic inputs from prior step outputs.
    2. Call AgentGuard-X → get verdict.
    3. Based on verdict: execute tool / sandbox / hard-stop.
    Returns True to continue, False to hard-stop the graph.
    """
    # ── Fill dynamic inputs from prior steps
    _fill_inputs(step, step_outputs)

    step.status = "running"
    step.started_at = time.time()
    await emit({"type": "step_update", "step": step.to_dict(), "workflow_id": ""})

    # ── AgentGuard-X check (fail-closed)
    guard = await check_with_guard(
        agent_id=step.agent_id,
        agent_role=step.agent_role,
        tool_name=step.tool_name,
        tool_input=step.tool_input,
    )
    step.verdict    = guard.get("verdict", "BLOCKED")
    step.risk_score = guard.get("risk_score", 1.0)
    step.guard_detail = guard

    security_event = {
        "step_id":    step.step_id,
        "agent_id":   step.agent_id,
        "tool_name":  step.tool_name,
        "verdict":    step.verdict,
        "risk_score": step.risk_score,
        "reason":     guard.get("reason", ""),
        "trace_id":   guard.get("trace_id", ""),
        "stage_detail": guard.get("stage_detail", []),
        "explanation": guard.get("explanation", ""),
        "timestamp":  time.time(),
    }
    security_events.append(security_event)

    await emit({"type": "security_verdict", "event": security_event})

    # ── Routing based on verdict
    if step.verdict == "BLOCK" or step.verdict == "BLOCKED":
        step.status      = "blocked"
        step.error       = f"Blocked by AgentGuard-X: {guard.get('reason', 'THREAT_DETECTED')}"
        step.reasoning   = f"AgentGuard-X issued BLOCK (score={step.risk_score:.3f}). Hard-stopping execution."
        step.completed_at = time.time()
        await emit({"type": "step_update", "step": step.to_dict()})
        await emit({"type": "execution_blocked",
                    "step_id": step.step_id,
                    "reason": step.error,
                    "guard": guard})
        return False  # hard stop

    elif step.verdict == "SANDBOX":
        sandbox_result = await _sandbox_evaluate(step)
        sandbox_verdict = sandbox_result.get("verdict", "BLOCK").upper()
        await emit({"type": "sandbox_result", "step_id": step.step_id,
                    "sandbox_verdict": sandbox_verdict, "detail": sandbox_result})
        if sandbox_verdict == "BLOCK":
            step.status    = "blocked"
            step.error     = f"Sandbox verdict: KILL — {sandbox_result.get('reason','')}"
            step.reasoning = "Sandbox evaluation returned KILL. Hard-stopping execution."
            step.completed_at = time.time()
            await emit({"type": "step_update", "step": step.to_dict()})
            return False
        # PROMOTE → treat as ALLOW and continue
        step.reasoning = f"Sandboxed execution promoted (safe). Continuing."
        result = execute_tool_sync(step.tool_name, step.tool_input)
        step.output    = result
        step.status    = "done"
        step.completed_at = time.time()

    else:  # ALLOW
        step.reasoning = f"AgentGuard-X ALLOW (score={step.risk_score:.3f}). Executing tool."
        result = execute_tool_sync(step.tool_name, step.tool_input)
        step.output    = result
        step.status    = "done"
        step.completed_at = time.time()

    await emit({"type": "step_update", "step": step.to_dict()})
    return True


def _fill_inputs(step: TaskNode, step_outputs: dict[str, Any]) -> None:
    """
    Replace placeholder values in step.tool_input with real output from prior steps.
    Convention: "[auto-populated from steps N-M outputs]" → build from available outputs.
    """
    for key, val in step.tool_input.items():
        if not isinstance(val, str) or "[auto-populated" not in val:
            continue

        if key == "content":
            parts = []
            for dep_id in step.depends_on:
                out = step_outputs.get(dep_id)
                if out:
                    data = out.get("data", out)
                    if isinstance(data, dict):
                        parts.append(json.dumps(data, indent=2))
                    else:
                        parts.append(str(data))
            step.tool_input[key] = "\n\n".join(parts) if parts else val

        elif key == "body":
            # Build email body from report step output
            for dep_id in step.depends_on:
                out = step_outputs.get(dep_id)
                if out and isinstance(out.get("data"), dict):
                    d = out["data"]
                    step.tool_input[key] = (
                        f"Please find the {step.tool_input.get('subject', 'report')} attached.\n\n"
                        f"Key metrics:\n{json.dumps(d, indent=2)[:800]}\n\n"
                        "Generated by FinanceFlow AI Platform."
                    )
                    break


async def execute_graph(
    graph: TaskGraph,
    emit: EmitFn,
) -> ExecutionResult:
    """
    Execute the task graph step by step.
    Emits real-time events for every state transition and security verdict.
    Hard-stops on BLOCK.
    """
    started_at = time.time()
    security_events: list[dict] = []
    outputs: list[dict] = []
    artifacts: list[str] = []
    step_outputs: dict[str, Any] = {}
    overall_status = "completed"

    await emit({"type": "execution_started", "graph": graph.to_dict()})

    for step in graph.steps:
        # Check all dependencies are done (not blocked/failed)
        for dep_id in step.depends_on:
            dep = next((s for s in graph.steps if s.step_id == dep_id), None)
            if dep and dep.status in ("blocked", "failed"):
                step.status = "blocked"
                step.error  = f"Dependency {dep_id} was blocked; skipping this step."
                await emit({"type": "step_update", "step": step.to_dict()})
                overall_status = "blocked"
                continue

        if step.status == "blocked":
            continue

        should_continue = await _execute_step(step, step_outputs, emit, security_events)

        if step.status == "done" and step.output:
            step_outputs[step.step_id] = step.output
            outputs.append({"step_id": step.step_id, "tool": step.tool_name,
                            "output": step.output, "source": step.output.get("source", "")})
            if step.output.get("artifact"):
                artifacts.append(step.output["artifact"])

        if not should_continue:
            overall_status = "blocked"
            # Mark remaining steps as blocked
            remaining = [s for s in graph.steps if s.status == "pending"]
            for s in remaining:
                s.status = "blocked"
                s.error  = "Upstream step was blocked by AgentGuard-X"
                await emit({"type": "step_update", "step": s.to_dict()})
            break

    completed_at = time.time()
    total_ms = round((completed_at - started_at) * 1000, 1)

    result = ExecutionResult(
        workflow_id=graph.workflow_id,
        status=overall_status,
        graph=graph,
        outputs=outputs,
        artifacts=artifacts,
        security_events=security_events,
        reasoning_chain=graph.reasoning_chain,
        started_at=started_at,
        completed_at=completed_at,
        total_ms=total_ms,
    )

    await emit({"type": "execution_complete", "result": result.to_dict()})
    return result


# ─── Public entry point ───────────────────────────────────────────────────────

async def run_query(
    query: str,
    session_id: str,
    emit: EmitFn,
    uploaded_context: str = "",
) -> ExecutionResult:
    """
    Full pipeline: classify → plan → execute.
    emit() is called for every event; use it to push to WebSocket.
    """
    wf_id = f"wf-{uuid.uuid4().hex[:10]}"
    intent = classify_intent(query)
    logger.info("Query intent: %s | query: %.80s", intent.value, query)

    graph = build_task_graph(query, session_id, intent, uploaded_context, workflow_id=wf_id)
    await emit({"type": "plan_ready", "graph": graph.to_dict(), "intent": intent.value})

    return await execute_graph(graph, emit)
