package agentguard.authz

# CRITICAL: Required for OPA < 1.0 — 'if' keyword is not built-in until OPA 1.0
import future.keywords.if

# ---------------------------------------------------------------------------
# FinanceFlow agent/tool permission matrix (RBAC via OPA)
#
# Stage 3 (stage3_policy.py) reads:
#   result.allow          (bool)
#   result.violation_type (string)
#   result.reason         (string, human-readable)
# ---------------------------------------------------------------------------

# Per-role tool allow-lists — must match agent_role values in REGISTERED_AGENTS
_allowed_tools := {
    "orchestrator_agent": {
        "delegate_task",
        "spawn_agent",
        "task_scheduler",
    },
    "orchestrator": {
        "delegate_task",
        "spawn_agent",
        "task_scheduler",
    },
    "research_agent": {
        "web_search",
        "read_pdf",
        "read_file",
        "scrape_webpage",
        "summarize_document",
        "financial_search",
        "sec_filings",
        "llm_answer",
    },
    "analyst_agent": {
        "query_internal_db",
        "write_report",
        "generate_summary",
        "create_financial_model",
        "generate_pdf",
        "llm_answer",
    },
    "report_agent": {
        "write_report",
        "send_email",
        "format_report",
        "export_pdf",
        "publish_report",
    },
    "data_agent": {
        "read_file",
        "http_post",
    },
    "admin_agent": {
        "web_search", "read_file", "http_post",
        "execute_shell", "query_internal_db",
        "write_report", "send_email", "spawn_agent",
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
# violation_type — mutually exclusive branches
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
