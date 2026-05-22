package agentguard.authz

# ---------------------------------------------------------------------------
# FinanceFlow agent/tool permission matrix
#
# Stage 3 (stage3_policy.py) reads:
#   result.allow          (bool)
#   result.violation_type (string, used to look up score in VIOLATION_SCORES)
#   result.reason         (string, human-readable)
#
# VIOLATION_SCORES in stage3_policy.py:
#   "tool_not_permitted"     → 0.90  (BLOCK zone)
#   "rate_limit_exceeded"    → 0.60  (SANDBOX zone)
#   "resource_scope_violation" → 0.75 (BLOCK zone)
# ---------------------------------------------------------------------------

# Per-role tool allow-lists
_allowed_tools := {
    "orchestrator": {
        "delegate_task",
        "spawn_agent",
        "task_scheduler",
    },
    "research_agent": {
        "web_search",
        "scrape_webpage",
        "read_pdf",
        "summarize_document",
    },
    "analyst_agent": {
        "query_internal_db",
        "generate_summary",
        "create_financial_model",
        "write_report",
    },
    "report_agent": {
        "format_report",
        "export_pdf",
        "publish_report",
        "send_email",
    },
}

_rate_limit_per_minute := 60

# ---------------------------------------------------------------------------
# Derived facts
# ---------------------------------------------------------------------------

_tool_permitted if {
    _allowed_tools[input.agent_role][input.tool_name]
}

_rate_exceeded if {
    input.request_count_last_minute > _rate_limit_per_minute
}

# ---------------------------------------------------------------------------
# allow — true only when tool is permitted AND rate is within limits
# ---------------------------------------------------------------------------

default allow := false

allow if {
    _tool_permitted
    not _rate_exceeded
}

# ---------------------------------------------------------------------------
# violation_type — mutually exclusive branches, no rule conflicts
# ---------------------------------------------------------------------------

default violation_type := ""

violation_type := "tool_not_permitted" if {
    not _tool_permitted
}

violation_type := "rate_limit_exceeded" if {
    _tool_permitted
    _rate_exceeded
}

# ---------------------------------------------------------------------------
# reason — human-readable message
# ---------------------------------------------------------------------------

default reason := ""

reason := "tool is permitted for this role" if {
    allow
}

reason := concat("", [
    "tool '", input.tool_name,
    "' is not in the allow-list for role '", input.agent_role, "'",
]) if {
    not _tool_permitted
}

reason := "request rate limit exceeded for this agent" if {
    _tool_permitted
    _rate_exceeded
}

# ---------------------------------------------------------------------------
# result — combined object consumed by stage3_policy.py
# ---------------------------------------------------------------------------

result := {
    "allow":          allow,
    "violation_type": violation_type,
    "reason":         reason,
}
