package agentguard.state_privilege

# ============================================================================
# State-Based Privilege Enforcement
# ============================================================================
#
# Context-aware rules that map (agent_role, tool_name, tool_context) → allow/deny
#
# Example:
#  - analyst_agent + query_internal_db + public_db → ALLOW
#  - analyst_agent + query_internal_db + admin_db → DENY
#  - research_agent + read_pdf + public_documents → ALLOW
#  - research_agent + read_pdf + internal_files → DENY
#
# This layer enforces the "where" after tool_rbac.rego enforces the "what"
#

default allow_context = false
default context_reason = "context check failed"

# ============================================================================
# ResearchAgent Context Rules
# ============================================================================
#
# Tool: read_pdf
# - Allowed contexts: public_documents
# - Denied contexts: internal_files, confidential_docs
#

allow_context if {
    input.agent_role == "research_agent"
    input.tool_name == "read_pdf"
    input.tool_context == "public_documents"
}

# ============================================================================
# AnalystAgent Context Rules
# ============================================================================
#
# Tool: query_internal_db
# - Allowed contexts: public_db, analytics_db
# - Denied contexts: admin_db, audit_trail, financial_accounts
#

allow_context if {
    input.agent_role == "analyst_agent"
    input.tool_name == "query_internal_db"
    input.tool_context in ["public_db", "analytics_db"]
}

#
# Tool: write_report
# - Allowed contexts: analytics_reports, temp_reports
# - Denied contexts: audit_trail, system_config, financial_statements
#

allow_context if {
    input.agent_role == "analyst_agent"
    input.tool_name == "write_report"
    input.tool_context in ["analytics_reports", "temp_reports"]
}

# ============================================================================
# ReportAgent Context Rules
# ============================================================================
#
# Tool: write_report
# - Allowed contexts: final_reports, email_reports
# - Denied contexts: system_config, audit_trail, draft_templates
#

allow_context if {
    input.agent_role == "report_agent"
    input.tool_name == "write_report"
    input.tool_context in ["final_reports", "email_reports"]
}

#
# Tool: send_email
# - Allowed contexts: internal_team, internal_distribution
# - Denied contexts: external_distribution, public_lists, vendor_emails
#

allow_context if {
    input.agent_role == "report_agent"
    input.tool_name == "send_email"
    input.tool_context in ["internal_team", "internal_distribution"]
}

# ============================================================================
# OrchestratorAgent Context Rules
# ============================================================================
#
# Tool: spawn_agent
# - Allowed contexts: standard_workflow
# - Denied contexts: emergency_override (requires special approval)
#

allow_context if {
    input.agent_role == "orchestrator_agent"
    input.tool_name == "spawn_agent"
    input.tool_context == "standard_workflow"
}

# ============================================================================
# Context Validation: Tool requires context to be evaluated
# ============================================================================
#
# Some tools REQUIRE context evaluation (e.g., read_pdf, query_internal_db)
# If context is missing, deny access
#

tools_requiring_context := {
    "read_pdf",
    "query_internal_db",
    "write_report",
    "send_email",
}

context_provided if {
    input.tool_context != ""
    input.tool_context != null
}

# ============================================================================
# COMPOSITE DECISION: Intent-Binding + State-Based
# ============================================================================
#
# Rule: If tool requires context, both checks must pass
# Rule: If tool doesn't require context, only intent-binding check needed
#

allow_composite if {
    # Tool doesn't require context checking
    not (input.tool_name in tools_requiring_context)
    
    # Intent-binding check passes (from tool_rbac.rego)
    data.agentguard.allow == true
}

allow_composite if {
    # Tool requires context checking
    input.tool_name in tools_requiring_context
    
    # Context is provided
    context_provided
    
    # Intent-binding check passes
    data.agentguard.allow == true
    
    # Context check passes
    allow_context == true
}

# ============================================================================
# REASON GENERATION: Why was access denied?
# ============================================================================
#

context_reason = "tool does not support this context" if {
    input.tool_name in tools_requiring_context
    allow_context == false
}

context_reason = "context not provided for tool requiring context" if {
    input.tool_name in tools_requiring_context
    not context_provided
}

context_reason = "no context-based restrictions apply" if {
    not (input.tool_name in tools_requiring_context)
}
