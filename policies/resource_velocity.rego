package agentguard.resource_velocity

# ============================================================================
# Resource & Velocity Enforcement
# ============================================================================
#
# Fine-grained velocity limits: per-role, per-tool, three tiers
# Tiers: per_sec, per_min, per_hour
#
# Soft limits: Routes request to SANDBOX mode
# Hard limits: Blocks request entirely (DENY)
#
# This layer enforces rate limits after intent-binding and state checks pass
#

default velocity_ok = false
default velocity_status = "unknown"
default velocity_reason = ""

# ============================================================================
# VELOCITY LIMITS: Per-Role, Per-Tool
# ============================================================================
#
# Format: role → tool → {soft: N, hard: N*2}
#
# Soft: Request allowed but monitored (route to SANDBOX if approaching)
# Hard: Request blocked immediately
#

velocity_config := {
    "orchestrator_agent": {
        "spawn_agent": {
            "per_sec": {"soft": 0.5, "hard": 1},
            "per_min": {"soft": 5, "hard": 10},
            "per_hour": {"soft": 50, "hard": 100},
        },
    },
    "research_agent": {
        "web_search": {
            "per_sec": {"soft": 3, "hard": 5},
            "per_min": {"soft": 60, "hard": 100},
            "per_hour": {"soft": 800, "hard": 1000},
        },
        "read_pdf": {
            "per_sec": {"soft": 2, "hard": 5},
            "per_min": {"soft": 40, "hard": 100},
            "per_hour": {"soft": 600, "hard": 1000},
        },
        "fetch_url": {
            "per_sec": {"soft": 5, "hard": 10},
            "per_min": {"soft": 100, "hard": 200},
            "per_hour": {"soft": 1000, "hard": 2000},
        },
    },
    "analyst_agent": {
        "query_internal_db": {
            "per_sec": {"soft": 5, "hard": 10},
            "per_min": {"soft": 120, "hard": 200},
            "per_hour": {"soft": 4000, "hard": 5000},
        },
        "write_report": {
            "per_sec": {"soft": 2, "hard": 10},
            "per_min": {"soft": 50, "hard": 200},
            "per_hour": {"soft": 4000, "hard": 5000},
        },
        "fetch_dataset": {
            "per_sec": {"soft": 3, "hard": 10},
            "per_min": {"soft": 80, "hard": 200},
            "per_hour": {"soft": 3000, "hard": 5000},
        },
    },
    "report_agent": {
        "write_report": {
            "per_sec": {"soft": 1.5, "hard": 3},
            "per_min": {"soft": 30, "hard": 50},
            "per_hour": {"soft": 400, "hard": 500},
        },
        "send_email": {
            "per_sec": {"soft": 1, "hard": 3},
            "per_min": {"soft": 20, "hard": 50},
            "per_hour": {"soft": 400, "hard": 500},
        },
    },
}

# Get velocity config for role+tool combination
get_velocity_limits(role, tool) = config if {
    config := velocity_config[role][tool]
}

# ============================================================================
# VELOCITY CHECK: Against provided current_call_count
# ============================================================================
#
# Input: {agent_role, tool_name, current_call_count_per_sec, per_min, per_hour}
# Output: {ok: bool, status: "ok"|"soft_limit"|"hard_limit", reason: "..."}
#

velocity_ok if {
    role := input.agent_role
    tool := input.tool_name
    
    # Get limits for this role+tool
    limits := get_velocity_limits(role, tool)
    
    # Check all three tiers
    check_velocity_tier(limits, "per_sec", input.current_call_count_per_sec)
    check_velocity_tier(limits, "per_min", input.current_call_count_per_min)
    check_velocity_tier(limits, "per_hour", input.current_call_count_per_hour)
}

# Check if current count exceeds hard limit (BLOCK)
hard_limit_exceeded if {
    role := input.agent_role
    tool := input.tool_name
    limits := get_velocity_limits(role, tool)
    (
        (input.current_call_count_per_sec >= limits["per_sec"]["hard"]) or
        (input.current_call_count_per_min >= limits["per_min"]["hard"]) or
        (input.current_call_count_per_hour >= limits["per_hour"]["hard"])
    )
}

# Check if current count exceeds soft limit (SANDBOX)
soft_limit_exceeded if {
    role := input.agent_role
    tool := input.tool_name
    limits := get_velocity_limits(role, tool)
    
    # Any tier exceeds soft limit but not hard limit
    (input.current_call_count_per_sec >= limits["per_sec"]["soft"] and
     input.current_call_count_per_sec < limits["per_sec"]["hard"]) or
    (input.current_call_count_per_min >= limits["per_min"]["soft"] and
     input.current_call_count_per_min < limits["per_min"]["hard"]) or
    (input.current_call_count_per_hour >= limits["per_hour"]["soft"] and
     input.current_call_count_per_hour < limits["per_hour"]["hard"])
}

# Helper: Check velocity for single tier
check_velocity_tier(limits, tier, current_count) {
    hard_limit := limits[tier]["hard"]
    soft_limit := limits[tier]["soft"]
    
    # Current count must be below hard limit
    current_count < hard_limit
}

# ============================================================================
# VELOCITY STATUS DETERMINATION
# ============================================================================
#

velocity_status = "hard_limit_exceeded" if {
    hard_limit_exceeded
}

velocity_status = "soft_limit_approaching" if {
    soft_limit_exceeded
    not hard_limit_exceeded
}

velocity_status = "ok" if {
    velocity_ok
    not soft_limit_exceeded
    not hard_limit_exceeded
}

velocity_status = "unknown" if {
    not velocity_ok
    not soft_limit_exceeded
    not hard_limit_exceeded
}

# ============================================================================
# VELOCITY REASON GENERATION
# ============================================================================
#

velocity_reason = "HARD LIMIT: hard rate limit exceeded" if {
    hard_limit_exceeded
}

velocity_reason = "SOFT LIMIT: approaching soft rate limit, routing to SANDBOX" if {
    soft_limit_exceeded
    not hard_limit_exceeded
}

velocity_reason = "VELOCITY OK: within all rate limits" if {
    velocity_ok
    not soft_limit_exceeded
}

# ============================================================================
# COMPOSITE VELOCITY DECISION
# ============================================================================
#
# Hard limit → DENY
# Soft limit → SANDBOX (allow but monitor/slow down)
# OK → Allow normal execution
#

allow_velocity if {
    not hard_limit_exceeded
}

route_to_sandbox if {
    soft_limit_exceeded
    not hard_limit_exceeded
}
