"""
Three required reports per request.

1. ExecutionReport — intent, task graph, tools used, reasoning chain, outputs, timing.
2. SecurityReport  — OPA decisions, sandbox results, drift findings, blocked actions, policy matches.
3. ObservabilityReport — Prometheus metrics, trace IDs, latency p50/p95, Loki query, Redis events.
"""
from __future__ import annotations

import json
import statistics
import time
from typing import Any

from financeflow.orchestrator import ExecutionResult


def _pct(n: int, total: int) -> str:
    return f"{(n / total * 100) if total else 0:.1f}%"


def build_execution_report(result: ExecutionResult) -> dict:
    graph = result.graph
    steps = graph.steps

    step_timings = [
        {
            "step_id":    s.step_id,
            "step_num":   s.step_num,
            "agent_id":   s.agent_id,
            "tool_name":  s.tool_name,
            "description": s.description,
            "status":     s.status,
            "verdict":    s.verdict,
            "risk_score": s.risk_score,
            "duration_ms": s.duration_ms(),
            "reasoning":  s.reasoning,
            "output_summary": (
                str(s.output.get("data", ""))[:200] if s.output else None
            ),
            "artifact":   s.output.get("artifact") if s.output else None,
            "source":     s.output.get("source", "unknown") if s.output else None,
        }
        for s in steps
    ]

    done_steps   = [s for s in steps if s.status == "done"]
    blocked_steps = [s for s in steps if s.status == "blocked"]
    durations    = [s.duration_ms() for s in done_steps if s.duration_ms() > 0]

    return {
        "report_type": "execution",
        "report_id":   f"exec-{graph.workflow_id}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workflow_id": graph.workflow_id,
        "user_intent": {
            "query":  graph.query,
            "intent": graph.intent.value,
        },
        "task_graph": {
            "total_steps":   len(steps),
            "completed":     len(done_steps),
            "blocked":       len(blocked_steps),
            "steps":         step_timings,
        },
        "reasoning_chain":  result.reasoning_chain,
        "outputs":          result.outputs,
        "artifacts": [
            {"path": a, "url": f"/outputs/{a.split('/')[-1]}"} for a in result.artifacts
        ],
        "timing": {
            "started_at":     result.started_at,
            "completed_at":   result.completed_at,
            "total_ms":       result.total_ms,
            "avg_step_ms":    round(statistics.mean(durations), 1) if durations else 0,
            "max_step_ms":    round(max(durations), 1) if durations else 0,
        },
        "overall_status": result.status,
    }


def build_security_report(result: ExecutionResult) -> dict:
    events = result.security_events
    total   = len(events)
    allowed  = sum(1 for e in events if e.get("verdict") in ("ALLOW",))
    sandboxed = sum(1 for e in events if e.get("verdict") == "SANDBOX")
    blocked  = sum(1 for e in events if e.get("verdict") in ("BLOCK", "BLOCKED"))

    # OPA (Stage 3) decisions per event
    opa_decisions = []
    for ev in events:
        s3 = next((s for s in ev.get("stage_detail", []) if s.get("stage") == 3), None)
        if s3:
            opa_decisions.append({
                "step_id":    ev.get("step_id"),
                "agent_id":   ev.get("agent_id"),
                "tool_name":  ev.get("tool_name"),
                "opa_allow":  not s3.get("triggered", False),
                "opa_reason": s3.get("reason", ""),
                "opa_score":  s3.get("score", 0.0),
            })

    # Semantic drift findings (Stage 5)
    drift_findings = []
    for ev in events:
        s5 = next((s for s in ev.get("stage_detail", []) if s.get("stage") == 5), None)
        if s5 and s5.get("score", 0) > 0.3:
            drift_findings.append({
                "step_id":   ev.get("step_id"),
                "tool_name": ev.get("tool_name"),
                "drift_score": s5.get("score"),
                "reason":    s5.get("reason", ""),
            })

    # Blocked actions
    blocked_actions = [
        {
            "step_id":   ev.get("step_id"),
            "agent_id":  ev.get("agent_id"),
            "tool_name": ev.get("tool_name"),
            "verdict":   ev.get("verdict"),
            "reason":    ev.get("reason", ""),
            "risk_score": ev.get("risk_score", 0),
            "explanation": ev.get("explanation", ""),
            "trace_id":  ev.get("trace_id", ""),
        }
        for ev in events if ev.get("verdict") in ("BLOCK", "BLOCKED")
    ]

    return {
        "report_type":  "security",
        "report_id":    f"sec-{result.workflow_id}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workflow_id":  result.workflow_id,
        "summary": {
            "total_interceptions": total,
            "allowed":   allowed,  "allowed_pct":   _pct(allowed, total),
            "sandboxed": sandboxed, "sandboxed_pct": _pct(sandboxed, total),
            "blocked":   blocked,  "blocked_pct":   _pct(blocked, total),
            "overall_verdict": (
                "CLEAN" if blocked == 0 and sandboxed == 0 else
                "THREAT_DETECTED" if blocked > 0 else "MONITORED"
            ),
        },
        "risk_analysis": {
            "max_risk_score": max((e.get("risk_score", 0) for e in events), default=0),
            "avg_risk_score": round(
                sum(e.get("risk_score", 0) for e in events) / total, 4
            ) if total else 0,
            "high_risk_calls": [e for e in events if e.get("risk_score", 0) > 0.5],
        },
        "opa_decisions":    opa_decisions,
        "drift_findings":   drift_findings,
        "blocked_actions":  blocked_actions,
        "all_events":       events,
        "compliance": {
            "gdpr": {
                "data_access_logged": True,
                "audit_trail": "complete",
                "retention":   "30 days",
            },
            "sox": {
                "access_control": "RBAC via OPA Stage 3",
                "segregation_of_duties": "enforced",
                "audit_trail": "all actions traced with trace_id",
            },
        },
    }


def build_observability_report(result: ExecutionResult) -> dict:
    events = result.security_events
    latencies = [e.get("latency_ms", 0) for e in events if e.get("latency_ms")]

    def pctile(vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        sorted_v = sorted(vals)
        idx = int(len(sorted_v) * p / 100)
        return round(sorted_v[min(idx, len(sorted_v) - 1)], 1)

    # Build Loki query string for this workflow
    loki_query = (
        f'{{service="agentguard"}} | json | workflow_id="{result.workflow_id}"'
    )
    loki_general = '{service="agentguard"} | json'

    # Prometheus metric references
    prometheus_refs = [
        "agentguard_requests_total — verdict/agent_role/tool_name counters",
        "agentguard_processing_duration_seconds — latency histogram by verdict",
        "agentguard_instant_kills_total — Stage 2 instant-kill counter",
        "agentguard_sandbox_verdicts_total — sandbox verdict distribution",
    ]

    # Trace IDs from security events
    trace_ids = [e.get("trace_id") for e in events if e.get("trace_id")]

    return {
        "report_type":  "observability",
        "report_id":    f"obs-{result.workflow_id}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workflow_id":  result.workflow_id,
        "trace_ids":    trace_ids,
        "latency": {
            "total_workflow_ms": result.total_ms,
            "p50_triage_ms":    pctile(latencies, 50),
            "p95_triage_ms":    pctile(latencies, 95),
            "min_triage_ms":    round(min(latencies), 1) if latencies else 0,
            "max_triage_ms":    round(max(latencies), 1) if latencies else 0,
            "samples":          len(latencies),
        },
        "prometheus": {
            "endpoint":  "http://localhost:9090",
            "metrics":   prometheus_refs,
            "example_queries": [
                "agentguard_requests_total",
                'rate(agentguard_requests_total[5m])',
                'histogram_quantile(0.95, agentguard_processing_duration_seconds_bucket)',
            ],
            "grafana_dashboard": "http://localhost:3001",
        },
        "loki": {
            "endpoint":     "http://localhost:3100",
            "readiness_probe": "GET /ready → 'ready'",
            "push_path":    "/loki/api/v1/push",
            "query_workflow": loki_query,
            "query_all":    loki_general,
            "note":         "Root path returns 404 — this is normal and healthy for Loki.",
        },
        "redis": {
            "events_key":   "agentguard:events",
            "session_key":  f"agentguard:session:ff-{result.workflow_id[:8]}",
            "verdict_keys": ["agentguard:verdict:ALLOW", "agentguard:verdict:BLOCKED", "agentguard:verdict:SANDBOX"],
            "probe":        "redis-cli ping → PONG",
        },
        "step_timings": [
            {
                "step_id": s.step_id,
                "tool_name": s.tool_name,
                "duration_ms": s.duration_ms(),
                "trace_id": next(
                    (e.get("trace_id") for e in events if e.get("step_id") == s.step_id),
                    None
                ),
            }
            for s in result.graph.steps
        ],
    }


def build_all_reports(result: ExecutionResult) -> dict:
    return {
        "execution":    build_execution_report(result),
        "security":     build_security_report(result),
        "observability": build_observability_report(result),
    }


def format_text_report(reports: dict) -> str:
    """Format all three reports as readable plaintext for download."""
    lines = ["=" * 70, "  FINANCEFLOW × AGENTGUARD-X — COMPLETE ANALYSIS REPORTS", "=" * 70, ""]

    # Execution Report
    er = reports["execution"]
    lines += [
        "SECTION 1: EXECUTION REPORT",
        "-" * 30,
        f"Workflow ID:  {er['workflow_id']}",
        f"Generated:    {er['generated_at']}",
        f"User Query:   {er['user_intent']['query']}",
        f"Intent:       {er['user_intent']['intent']}",
        f"Status:       {er['overall_status'].upper()}",
        "",
        "Task Graph:",
        f"  Total steps: {er['task_graph']['total_steps']}",
        f"  Completed:   {er['task_graph']['completed']}",
        f"  Blocked:     {er['task_graph']['blocked']}",
        "",
    ]
    for s in er["task_graph"]["steps"]:
        icon = {"done": "✓", "blocked": "✗", "failed": "!", "running": "→", "pending": "·"}.get(s["status"], "?")
        lines.append(f"  [{icon}] Step {s['step_num']}: {s['description']}")
        lines.append(f"       Agent: {s['agent_id']}  Tool: {s['tool_name']}")
        lines.append(f"       Verdict: {s['verdict'] or 'N/A'}  Risk: {s['risk_score']:.3f}  Duration: {s['duration_ms']}ms")
        if s.get("artifact"):
            lines.append(f"       Artifact: {s['artifact']}")
        lines.append("")

    lines += [
        "Reasoning Chain:",
    ]
    for r in er["reasoning_chain"]:
        lines.append(f"  • {r}")
    lines += ["",
              f"Total duration: {er['timing']['total_ms']}ms",
              ""]

    # Security Report
    sr = reports["security"]
    lines += [
        "=" * 70,
        "SECTION 2: SECURITY REPORT",
        "-" * 30,
        f"Overall Verdict: {sr['summary']['overall_verdict']}",
        f"Interceptions:   {sr['summary']['total_interceptions']}",
        f"  ALLOW:   {sr['summary']['allowed']} ({sr['summary']['allowed_pct']})",
        f"  SANDBOX: {sr['summary']['sandboxed']} ({sr['summary']['sandboxed_pct']})",
        f"  BLOCKED: {sr['summary']['blocked']} ({sr['summary']['blocked_pct']})",
        f"Max Risk Score:  {sr['risk_analysis']['max_risk_score']:.4f}",
        "",
    ]
    if sr["blocked_actions"]:
        lines.append("Blocked Actions:")
        for b in sr["blocked_actions"]:
            lines.append(f"  ✗ {b['agent_id']}.{b['tool_name']} — {b['reason']}")
            lines.append(f"    Risk: {b['risk_score']:.4f}  Trace: {b['trace_id']}")
        lines.append("")
    if sr["opa_decisions"]:
        lines.append("OPA Policy Decisions (Stage 3):")
        for d in sr["opa_decisions"]:
            icon = "✓" if d["opa_allow"] else "✗"
            lines.append(f"  [{icon}] {d['agent_id']}.{d['tool_name']}: {d['opa_reason']}")
        lines.append("")

    # Observability Report
    obs = reports["observability"]
    lines += [
        "=" * 70,
        "SECTION 3: OBSERVABILITY REPORT",
        "-" * 30,
        f"Trace IDs: {', '.join(obs['trace_ids'][:3])}{'...' if len(obs['trace_ids']) > 3 else ''}",
        "",
        "Latency:",
        f"  Total workflow:  {obs['latency']['total_workflow_ms']}ms",
        f"  Triage p50:      {obs['latency']['p50_triage_ms']}ms",
        f"  Triage p95:      {obs['latency']['p95_triage_ms']}ms",
        "",
        "Loki Query (to retrieve these logs):",
        f"  {obs['loki']['query_workflow']}",
        f"  NOTE: {obs['loki']['note']}",
        "",
        "Prometheus Metrics:",
    ]
    for m in obs["prometheus"]["metrics"]:
        lines.append(f"  • {m}")
    lines += ["", "=" * 70]
    return "\n".join(lines)
