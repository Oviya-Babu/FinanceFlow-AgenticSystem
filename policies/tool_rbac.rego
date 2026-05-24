package agentguard

# ============================================================================
# AgentGuard RBAC Policy Engine - FinanceFlow Production System
# ============================================================================
# 
# Default Deny: All access is denied unless explicitly allowed by policy
# This file defines:
#  - Agent role definitions (4 FinanceFlow agents)
#  - Tool allowlists and denylists
#  - Regex pattern matching for tool families
#  - Basic velocity limits (per-role aggregates)
#  - Context-aware tool restrictions
#  - Time-based permissions
#
# State-based privilege rules and fine-grained velocity are in separate files.
# ============================================================================

# Default: Deny all access (fail-closed)
default allow = false
default decision_trace = []

# ============================================================================
# AGENT METADATA: FinanceFlow System (4 Agents)
# ============================================================================
# 
# OrchestratorAgent:  Spawns and manages other agents
# ResearchAgent:      Performs web search and document analysis
# AnalystAgent:       Queries internal databases and generates analytics
# ReportAgent:        Generates reports and sends notifications
#

agent_metadata := {
    "orchestrator_agent": {
        "description": "Orchestrates workflow, spawns research/analyst/report agents",
        "team": "finance",
        "level": "orchestration",
        "parent": null,
    },
    "research_agent": {
        "description": "Performs web search and PDF document analysis",
        "team": "finance",
        "level": "worker",
        "parent": "orchestrator_agent",
    },
    "analyst_agent": {
        "description": "Queries internal databases and generates analytics",
        "team": "finance",
        "level": "worker",
        "parent": "orchestrator_agent",
    },
    "report_agent": {
        "description": "Generates reports and sends notifications",
        "team": "finance",
        "level": "worker",
        "parent": "orchestrator_agent",
    },
}

# ============================================================================
# INTENT-BINDING RULES: Tool Allowlists per Agent Role
# ============================================================================
# 
# Maps agent role → {allowed_tools}
# Uses exact matching and regex patterns (e.g., "read_file.*" matches read_file_config)
# 

role_tool_allowlist := {
    # OrchestratorAgent: Only spawn other agents
    "orchestrator_agent": [
        "spawn_agent",  # Exact match
    ],
    
    # ResearchAgent: Web search and document analysis
    "research_agent": [
        "web_search",   # Exact match
        "read_pdf",     # Exact match (restricted by context)
        "fetch_url",    # Exact match
    ],
    
    # AnalystAgent: Internal database queries and reporting
    "analyst_agent": [
        "query_internal_db",    # Exact match (restricted by context)
        "write_report",         # Exact match (restricted by context)
        "fetch_dataset",        # Exact match
    ],
    
    # ReportAgent: Final reporting and notifications
    "report_agent": [
        "write_report",         # Exact match (restricted by context)
        "send_email",          # Exact match (restricted by context)
    ],
}

# Tool denylist: Explicitly forbidden tools (supercedes allowlist)
role_tool_denylist := {
    "orchestrator_agent": [
        "web_search", "read_pdf", "fetch_url",
        "query_internal_db", "write_report", "send_email",
        "fetch_dataset", "write_memory", "delete_memory",
    ],
    "research_agent": [
        "query_internal_db", "write_report", "send_email",
        "spawn_agent", "fetch_dataset",
    ],
    "analyst_agent": [
        "web_search", "read_pdf", "fetch_url",
        "send_email", "spawn_agent",
    ],
    "report_agent": [
        "web_search", "read_pdf", "fetch_url",
        "query_internal_db", "fetch_dataset", "spawn_agent",
    ],
}

# ============================================================================
# REGEX PATTERN MATCHING: Tool Family Rules
# ============================================================================
#
# Some tools use wildcards: read_file.*, write_file.*
# These patterns allow matching entire tool families
#

pattern_based_tools := {
    "read_file.*": {
        "description": "Read operations on any file type",
        "allowed_for": ["research_agent", "analyst_agent"],
    },
    "write_file.*": {
        "description": "Write operations on any file type",
        "allowed_for": [],  # No agent can write files directly
    },
}

# Check if tool matches any pattern
tool_matches_pattern(tool_name, pattern) if {
    endswith(pattern, ".*")
    prefix := substring(pattern, 0, count(pattern) - 2)
    startswith(tool_name, prefix)
}

# ============================================================================
# BASIC INTENT-BINDING: Tool Allowlist Check
# ============================================================================
# 
# Step 1: Check denylist (explicit deny supercedes allow)
# Step 2: Check allowlist (exact match or pattern match)
#

allow_basic if {
    agent_role := input.agent_role
    tool_name := input.tool_name
    not tool_in_denylist(agent_role, tool_name)
    tool_in_allowlist(agent_role, tool_name)
}

allow_basic if {
    agent_role := input.agent_role
    tool_name := input.tool_name
    not tool_in_denylist(agent_role, tool_name)
    pattern := object.keys(pattern_based_tools)[_]
    tool_matches_pattern(tool_name, pattern)
    agent_role in pattern_based_tools[pattern]["allowed_for"]
}

tool_in_allowlist(role, tool) if {
    tool in role_tool_allowlist[role]
}

tool_in_denylist(role, tool) if {
    tool in role_tool_denylist[role]
}

# ============================================================================
# BASIC VELOCITY LIMITS: Per-Role Aggregates
# ============================================================================
#
# Coarse-grained limits (per role, not per tool)
# Fine-grained limits are in resource_velocity.rego
#

velocity_limits := {
    "orchestrator_agent": {
        "per_sec": 1,
        "per_min": 10,
        "per_hour": 100,
        "description": "Orchestrator: 1 spawn/sec, 10/min, 100/hour",
    },
    "research_agent": {
        "per_sec": 5,
        "per_min": 100,
        "per_hour": 1000,
        "description": "Research: 5 calls/sec, 100/min, 1K/hour",
    },
    "analyst_agent": {
        "per_sec": 10,
        "per_min": 200,
        "per_hour": 5000,
        "description": "Analyst: 10 calls/sec, 200/min, 5K/hour",
    },
    "report_agent": {
        "per_sec": 3,
        "per_min": 50,
        "per_hour": 500,
        "description": "Report: 3 calls/sec, 50/min, 500/hour",
    },
}

# Get velocity limit for role
velocity_limit = limit if {
    limit := velocity_limits[input.agent_role]
}

velocity_limit = {"per_sec": 5, "per_min": 100, "per_hour": 1000} if {
    not velocity_limits[input.agent_role]
}

# ============================================================================
# TIME-BASED PERMISSIONS
# ============================================================================
#
# Some tools may be restricted to business hours
# Format: "business_hours_only" flag
#

time_restricted_tools := {
    "send_email": {
        "restriction": "business_hours_only",
        "allowed_hours": "09:00-18:00",  # UTC
        "allowed_days": "Mon-Fri",
    },
}

# ============================================================================
# MAIN DECISION POINT
# ============================================================================
#
# Primary rule: Use basic intent-binding check
# Return both decision and trace for debugging
#

allow if {
    allow_basic
}

# Trace for debugging (shows which rule matched)
decision_trace = [{
    "stage": "intent_binding",
    "agent_role": input.agent_role,
    "tool_name": input.tool_name,
    "result": "allow",
    "reason": "Tool in allowlist for agent role",
}] if {
    allow_basic
}

# Deny trace (default)
decision_trace = [{
    "stage": "intent_binding",
    "agent_role": input.agent_role,
    "tool_name": input.tool_name,
    "result": "deny",
    "reason": "Tool not in allowlist or in denylist",
}] if {
    not allow_basic
}

# ============================================================================
# HELPER: Check if agent exists in metadata
# ============================================================================

agent_exists(agent_id) {
    agent_id in object.keys(agent_metadata)
}

# ============================================================================
# HELPER: Get agent role from agent_id
# ============================================================================

get_agent_role(agent_id) = agent_id  # For now, agent_id IS the role
