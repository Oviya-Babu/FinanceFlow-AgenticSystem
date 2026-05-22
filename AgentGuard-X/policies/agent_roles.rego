package agentguard.authz

# Tool allowlists per role
allowed_tools := {
    "research_agent": {"web_search", "read_file"},
    "data_agent":     {"read_file", "http_post"},
    "admin_agent":    {"web_search", "read_file", "http_post", "execute_shell"}
}

# Rate limits per role (requests per minute)
rate_limits := {
    "research_agent": 30,
    "data_agent":     20,
    "admin_agent":    10
}

default allow = false
default reason = "default deny"
default violation_type = "unknown"

allow if {
    input.tool_name in allowed_tools[input.agent_role]
    input.request_count_last_minute < rate_limits[input.agent_role]
}

reason = "Tool not permitted for this agent role" if {
    not input.tool_name in allowed_tools[input.agent_role]
}

violation_type = "tool_not_permitted" if {
    not input.tool_name in allowed_tools[input.agent_role]
}

reason = "Rate limit exceeded" if {
    input.request_count_last_minute >= rate_limits[input.agent_role]
}

violation_type = "rate_limit_exceeded" if {
    input.request_count_last_minute >= rate_limits[input.agent_role]
}
