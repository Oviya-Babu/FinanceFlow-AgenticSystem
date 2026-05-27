package agentguard.roles

# CRITICAL: Required for OPA < 1.0 — 'if' and 'in' keywords are not built-in
import future.keywords.if
import future.keywords.in

allowed_tools := {
    "orchestrator_agent": {"spawn_agent"},
    "research_agent":     {"web_search", "read_pdf", "read_file"},
    "analyst_agent":      {"query_internal_db", "write_report"},
    "report_agent":       {"write_report", "send_email"},
    "data_agent":         {"read_file", "http_post"},
    "admin_agent":        {"web_search", "read_file", "http_post",
                           "execute_shell", "query_internal_db",
                           "write_report", "send_email", "spawn_agent"}
}

rate_limits := {
    "orchestrator_agent": 20,
    "research_agent":     30,
    "analyst_agent":      20,
    "report_agent":       10,
    "data_agent":         20,
    "admin_agent":        10
}

high_risk_tools := {"execute_shell", "spawn_agent", "query_internal_db"}

known_roles := {
    "orchestrator_agent", "research_agent", "analyst_agent",
    "report_agent", "data_agent", "admin_agent"
}

default allow          = false
default violation_type = "unknown"
default reason         = "Request denied by default policy"
default risk_boost     = 0.0

allow if {
    input.tool_name in allowed_tools[input.agent_role]
    input.request_count_last_minute < rate_limits[input.agent_role]
}

violation_type = "tool_not_permitted" if {
    input.agent_role in known_roles
    not input.tool_name in allowed_tools[input.agent_role]
}

reason = msg if {
    input.agent_role in known_roles
    not input.tool_name in allowed_tools[input.agent_role]
    msg := sprintf("Role '%v' cannot call tool '%v'. Allowed: %v",
        [input.agent_role, input.tool_name, allowed_tools[input.agent_role]])
}

violation_type = "rate_limit_exceeded" if {
    input.request_count_last_minute >= rate_limits[input.agent_role]
}

reason = msg if {
    input.request_count_last_minute >= rate_limits[input.agent_role]
    msg := sprintf("Rate limit exceeded for '%v'. Made %v requests (limit: %v/min)",
        [input.agent_role, input.request_count_last_minute, rate_limits[input.agent_role]])
}

violation_type = "unknown_role" if {
    not input.agent_role in known_roles
}

reason = "Unknown agent role — no policy defined. Defaulting to deny." if {
    not input.agent_role in known_roles
}

risk_boost = 0.2 if {
    input.tool_name in high_risk_tools
    allow
}
