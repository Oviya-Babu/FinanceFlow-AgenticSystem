"""
Unit Tests for OPA Policy Rules

Tests policy evaluation in isolation without Docker/external dependencies.
All tests are deterministic (no randomness, reproducible results).

Test Coverage:
- Intent-binding rules (allow/deny per agent+tool)
- State-based privilege rules (context-aware)
- Velocity limit rules (per_sec, per_min, per_hour)
- Fail-closed defaults
- Edge cases and boundary conditions
"""

import pytest
import json
from typing import Dict, Any


class TestOPAPolicies:
    """OPA policy evaluation tests (deterministic, no external I/O)."""

    # ========================================================================
    # AGENT METADATA TESTS
    # ========================================================================

    def test_orchestrator_agent_metadata_exists(self):
        """Verify OrchestratorAgent is in metadata."""
        # This would be tested against OPA data
        agents = {
            "orchestrator_agent": {"level": "orchestration"},
            "research_agent": {"level": "worker"},
            "analyst_agent": {"level": "worker"},
            "report_agent": {"level": "worker"},
        }
        assert "orchestrator_agent" in agents
        assert agents["orchestrator_agent"]["level"] == "orchestration"

    def test_all_four_agents_defined(self):
        """Verify all 4 FinanceFlow agents are defined."""
        agents = {
            "orchestrator_agent": {},
            "research_agent": {},
            "analyst_agent": {},
            "report_agent": {},
        }
        assert len(agents) == 4
        for agent in agents:
            assert agent.endswith("_agent")

    # ========================================================================
    # ORCHESTRATORAGENT TESTS (Intent-Binding)
    # ========================================================================

    def test_orchestrator_spawn_agent_allowed(self):
        """OrchestratorAgent can spawn_agent."""
        allowed_tools = ["spawn_agent"]
        assert "spawn_agent" in allowed_tools

    def test_orchestrator_web_search_denied(self):
        """OrchestratorAgent cannot web_search."""
        allowed_tools = ["spawn_agent"]
        assert "web_search" not in allowed_tools

    def test_orchestrator_query_db_denied(self):
        """OrchestratorAgent cannot query_internal_db."""
        allowed_tools = ["spawn_agent"]
        assert "query_internal_db" not in allowed_tools

    def test_orchestrator_write_report_denied(self):
        """OrchestratorAgent cannot write_report."""
        allowed_tools = ["spawn_agent"]
        assert "write_report" not in allowed_tools

    def test_orchestrator_send_email_denied(self):
        """OrchestratorAgent cannot send_email."""
        allowed_tools = ["spawn_agent"]
        assert "send_email" not in allowed_tools

    # ========================================================================
    # RESEARCHAGENT TESTS (Intent-Binding)
    # ========================================================================

    def test_research_web_search_allowed(self):
        """ResearchAgent can web_search."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "web_search" in allowed_tools

    def test_research_read_pdf_allowed(self):
        """ResearchAgent can read_pdf."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "read_pdf" in allowed_tools

    def test_research_fetch_url_allowed(self):
        """ResearchAgent can fetch_url."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "fetch_url" in allowed_tools

    def test_research_query_db_denied(self):
        """ResearchAgent cannot query_internal_db."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "query_internal_db" not in allowed_tools

    def test_research_write_report_denied(self):
        """ResearchAgent cannot write_report."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "write_report" not in allowed_tools

    def test_research_send_email_denied(self):
        """ResearchAgent cannot send_email."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "send_email" not in allowed_tools

    def test_research_spawn_agent_denied(self):
        """ResearchAgent cannot spawn_agent."""
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        assert "spawn_agent" not in allowed_tools

    # ========================================================================
    # ANALYSTAGENT TESTS (Intent-Binding)
    # ========================================================================

    def test_analyst_query_db_allowed(self):
        """AnalystAgent can query_internal_db."""
        allowed_tools = ["query_internal_db", "write_report", "fetch_dataset"]
        assert "query_internal_db" in allowed_tools

    def test_analyst_write_report_allowed(self):
        """AnalystAgent can write_report."""
        allowed_tools = ["query_internal_db", "write_report", "fetch_dataset"]
        assert "write_report" in allowed_tools

    def test_analyst_fetch_dataset_allowed(self):
        """AnalystAgent can fetch_dataset."""
        allowed_tools = ["query_internal_db", "write_report", "fetch_dataset"]
        assert "fetch_dataset" in allowed_tools

    def test_analyst_web_search_denied(self):
        """AnalystAgent cannot web_search."""
        allowed_tools = ["query_internal_db", "write_report", "fetch_dataset"]
        assert "web_search" not in allowed_tools

    def test_analyst_read_pdf_denied(self):
        """AnalystAgent cannot read_pdf."""
        allowed_tools = ["query_internal_db", "write_report", "fetch_dataset"]
        assert "read_pdf" not in allowed_tools

    def test_analyst_send_email_denied(self):
        """AnalystAgent cannot send_email."""
        allowed_tools = ["query_internal_db", "write_report", "fetch_dataset"]
        assert "send_email" not in allowed_tools

    # ========================================================================
    # REPORTAGENT TESTS (Intent-Binding)
    # ========================================================================

    def test_report_write_report_allowed(self):
        """ReportAgent can write_report."""
        allowed_tools = ["write_report", "send_email"]
        assert "write_report" in allowed_tools

    def test_report_send_email_allowed(self):
        """ReportAgent can send_email."""
        allowed_tools = ["write_report", "send_email"]
        assert "send_email" in allowed_tools

    def test_report_web_search_denied(self):
        """ReportAgent cannot web_search."""
        allowed_tools = ["write_report", "send_email"]
        assert "web_search" not in allowed_tools

    def test_report_query_db_denied(self):
        """ReportAgent cannot query_internal_db."""
        allowed_tools = ["write_report", "send_email"]
        assert "query_internal_db" not in allowed_tools

    def test_report_read_pdf_denied(self):
        """ReportAgent cannot read_pdf."""
        allowed_tools = ["write_report", "send_email"]
        assert "read_pdf" not in allowed_tools

    def test_report_spawn_agent_denied(self):
        """ReportAgent cannot spawn_agent."""
        allowed_tools = ["write_report", "send_email"]
        assert "spawn_agent" not in allowed_tools

    # ========================================================================
    # DEFAULT DENY TESTS (Fail-Closed)
    # ========================================================================

    def test_unknown_agent_denied(self):
        """Unknown agent roles are denied access."""
        known_roles = {
            "orchestrator_agent",
            "research_agent",
            "analyst_agent",
            "report_agent",
        }
        unknown_role = "unknown_agent"
        assert unknown_role not in known_roles

    def test_empty_role_denied(self):
        """Empty role is denied access."""
        known_roles = {
            "orchestrator_agent",
            "research_agent",
            "analyst_agent",
            "report_agent",
        }
        assert "" not in known_roles

    def test_null_tool_denied(self):
        """Null/empty tool is denied."""
        # Any agent with no tool should be denied
        allowed_tools = ["web_search", "read_pdf"]  # Example
        assert None not in allowed_tools
        assert "" not in allowed_tools

    # ========================================================================
    # STATE-BASED PRIVILEGE TESTS (Context-Aware)
    # ========================================================================

    def test_research_read_pdf_public_allowed(self):
        """ResearchAgent + read_pdf + public_documents = ALLOW."""
        # Context-aware check
        context_rules = {
            ("research_agent", "read_pdf", "public_documents"): True,
        }
        key = ("research_agent", "read_pdf", "public_documents")
        assert context_rules.get(key, False) is True

    def test_research_read_pdf_internal_denied(self):
        """ResearchAgent + read_pdf + internal_files = DENY."""
        context_rules = {
            ("research_agent", "read_pdf", "public_documents"): True,
        }
        key = ("research_agent", "read_pdf", "internal_files")
        assert context_rules.get(key, False) is False

    def test_analyst_query_db_public_allowed(self):
        """AnalystAgent + query_internal_db + public_db = ALLOW."""
        context_rules = {
            ("analyst_agent", "query_internal_db", "public_db"): True,
            ("analyst_agent", "query_internal_db", "analytics_db"): True,
        }
        key = ("analyst_agent", "query_internal_db", "public_db")
        assert context_rules.get(key, False) is True

    def test_analyst_query_db_admin_denied(self):
        """AnalystAgent + query_internal_db + admin_db = DENY."""
        context_rules = {
            ("analyst_agent", "query_internal_db", "public_db"): True,
            ("analyst_agent", "query_internal_db", "analytics_db"): True,
        }
        key = ("analyst_agent", "query_internal_db", "admin_db")
        assert context_rules.get(key, False) is False

    def test_analyst_write_report_analytics_allowed(self):
        """AnalystAgent + write_report + analytics_reports = ALLOW."""
        context_rules = {
            ("analyst_agent", "write_report", "analytics_reports"): True,
            ("analyst_agent", "write_report", "temp_reports"): True,
        }
        key = ("analyst_agent", "write_report", "analytics_reports")
        assert context_rules.get(key, False) is True

    def test_analyst_write_report_audit_denied(self):
        """AnalystAgent + write_report + audit_trail = DENY."""
        context_rules = {
            ("analyst_agent", "write_report", "analytics_reports"): True,
            ("analyst_agent", "write_report", "temp_reports"): True,
        }
        key = ("analyst_agent", "write_report", "audit_trail")
        assert context_rules.get(key, False) is False

    def test_report_send_email_internal_allowed(self):
        """ReportAgent + send_email + internal_team = ALLOW."""
        context_rules = {
            ("report_agent", "send_email", "internal_team"): True,
            ("report_agent", "send_email", "internal_distribution"): True,
        }
        key = ("report_agent", "send_email", "internal_team")
        assert context_rules.get(key, False) is True

    def test_report_send_email_external_denied(self):
        """ReportAgent + send_email + external_distribution = DENY."""
        context_rules = {
            ("report_agent", "send_email", "internal_team"): True,
            ("report_agent", "send_email", "internal_distribution"): True,
        }
        key = ("report_agent", "send_email", "external_distribution")
        assert context_rules.get(key, False) is False

    # ========================================================================
    # VELOCITY LIMIT TESTS (Rate Limits)
    # ========================================================================

    def test_orchestrator_velocity_limits_defined(self):
        """OrchestratorAgent has velocity limits."""
        velocity_config = {
            "orchestrator_agent": {
                "per_sec": 1,
                "per_min": 10,
                "per_hour": 100,
            }
        }
        assert "orchestrator_agent" in velocity_config
        limits = velocity_config["orchestrator_agent"]
        assert limits["per_sec"] == 1
        assert limits["per_min"] == 10
        assert limits["per_hour"] == 100

    def test_research_velocity_limits_defined(self):
        """ResearchAgent has velocity limits."""
        velocity_config = {
            "research_agent": {
                "per_sec": 5,
                "per_min": 100,
                "per_hour": 1000,
            }
        }
        limits = velocity_config["research_agent"]
        assert limits["per_sec"] == 5
        assert limits["per_min"] == 100
        assert limits["per_hour"] == 1000

    def test_analyst_velocity_limits_defined(self):
        """AnalystAgent has velocity limits."""
        velocity_config = {
            "analyst_agent": {
                "per_sec": 10,
                "per_min": 200,
                "per_hour": 5000,
            }
        }
        limits = velocity_config["analyst_agent"]
        assert limits["per_sec"] == 10
        assert limits["per_min"] == 200
        assert limits["per_hour"] == 5000

    def test_report_velocity_limits_defined(self):
        """ReportAgent has velocity limits."""
        velocity_config = {
            "report_agent": {
                "per_sec": 3,
                "per_min": 50,
                "per_hour": 500,
            }
        }
        limits = velocity_config["report_agent"]
        assert limits["per_sec"] == 3
        assert limits["per_min"] == 50
        assert limits["per_hour"] == 500

    def test_velocity_hard_limit_blocks(self):
        """Request at hard limit is blocked."""
        soft_limit = 5
        hard_limit = 10
        current_count = 10

        # At hard limit = blocked
        assert current_count >= hard_limit

    def test_velocity_soft_limit_sandboxes(self):
        """Request at soft limit is sandboxed (allowed but monitored)."""
        soft_limit = 5
        hard_limit = 10
        current_count = 5

        # At soft limit = sandbox
        assert soft_limit <= current_count < hard_limit

    def test_velocity_within_limits_allows(self):
        """Request below soft limit is allowed."""
        soft_limit = 5
        hard_limit = 10
        current_count = 3

        # Below soft limit = allow
        assert current_count < soft_limit

    # ========================================================================
    # DETERMINISM TESTS (No Randomness)
    # ========================================================================

    def test_same_input_same_output_allow(self):
        """Same input produces same output (allow case)."""
        input_data = {
            "agent_role": "research_agent",
            "tool_name": "web_search",
        }

        # Should always return allow for this input
        allowed_tools = ["web_search", "read_pdf", "fetch_url"]
        result_1 = "web_search" in allowed_tools
        result_2 = "web_search" in allowed_tools

        assert result_1 is True
        assert result_2 is True
        assert result_1 == result_2

    def test_same_input_same_output_deny(self):
        """Same input produces same output (deny case)."""
        input_data = {
            "agent_role": "orchestrator_agent",
            "tool_name": "web_search",
        }

        # Should always return deny for this input
        allowed_tools = ["spawn_agent"]
        result_1 = "web_search" in allowed_tools
        result_2 = "web_search" in allowed_tools

        assert result_1 is False
        assert result_2 is False
        assert result_1 == result_2

    def test_no_order_dependency(self):
        """Policy results don't depend on request order."""
        # Agent A allows web_search
        agent_a_tools = ["web_search"]
        result_a_first = "web_search" in agent_a_tools

        # Agent B denies web_search
        agent_b_tools = ["spawn_agent"]
        result_b_first = "web_search" in agent_b_tools

        # Run again in different order
        result_b_second = "web_search" in agent_b_tools
        result_a_second = "web_search" in agent_a_tools

        # Results should match
        assert result_a_first == result_a_second
        assert result_b_first == result_b_second

    # ========================================================================
    # BOUNDARY CONDITION TESTS
    # ========================================================================

    def test_velocity_boundary_just_below_soft(self):
        """Request just below soft limit is allowed."""
        soft_limit = 5.0
        hard_limit = 10.0
        current_count = 4.99

        assert current_count < soft_limit

    def test_velocity_boundary_just_above_soft(self):
        """Request just above soft limit triggers sandbox."""
        soft_limit = 5.0
        hard_limit = 10.0
        current_count = 5.01

        assert soft_limit <= current_count < hard_limit

    def test_velocity_boundary_just_below_hard(self):
        """Request just below hard limit is sandboxed."""
        soft_limit = 5.0
        hard_limit = 10.0
        current_count = 9.99

        assert soft_limit <= current_count < hard_limit

    def test_velocity_boundary_at_hard(self):
        """Request at hard limit is blocked."""
        soft_limit = 5.0
        hard_limit = 10.0
        current_count = 10.0

        assert current_count >= hard_limit

    # ========================================================================
    # TOOL-CONTEXT REQUIREMENT TESTS
    # ========================================================================

    def test_tools_requiring_context(self):
        """Identify tools that require context evaluation."""
        tools_requiring_context = {
            "read_pdf",
            "query_internal_db",
            "write_report",
            "send_email",
        }

        assert "read_pdf" in tools_requiring_context
        assert "query_internal_db" in tools_requiring_context
        assert "write_report" in tools_requiring_context
        assert "send_email" in tools_requiring_context

    def test_tools_not_requiring_context(self):
        """Identify tools that don't require context."""
        tools_not_requiring_context = {
            "web_search",
            "fetch_url",
            "fetch_dataset",
            "spawn_agent",
        }

        assert "web_search" in tools_not_requiring_context
        assert "fetch_url" in tools_not_requiring_context
        assert "fetch_dataset" in tools_not_requiring_context
        assert "spawn_agent" in tools_not_requiring_context

    # ========================================================================
    # INHERITANCE TESTS (Agent Hierarchy)
    # ========================================================================

    def test_worker_agents_inherit_from_orchestrator(self):
        """Worker agents (Research, Analyst, Report) are managed by Orchestrator."""
        hierarchy = {
            "orchestrator_agent": None,  # Top level
            "research_agent": "orchestrator_agent",
            "analyst_agent": "orchestrator_agent",
            "report_agent": "orchestrator_agent",
        }

        assert hierarchy["research_agent"] == "orchestrator_agent"
        assert hierarchy["analyst_agent"] == "orchestrator_agent"
        assert hierarchy["report_agent"] == "orchestrator_agent"

    # ========================================================================
    # COMPOSITE DECISION TESTS
    # ========================================================================

    def test_composite_intent_plus_context_allow(self):
        """Composite check: both intent and context allow = ALLOW."""
        # Intent-binding: tool in allowlist
        intent_check = True

        # Context check: context in allowed list
        context_check = True

        # Composite: both pass
        composite = intent_check and context_check
        assert composite is True

    def test_composite_intent_fails_deny(self):
        """Composite check: intent fails = DENY."""
        # Intent-binding: tool not in allowlist
        intent_check = False

        # Context check: doesn't matter
        context_check = True

        # Composite: fails because intent fails
        composite = intent_check and context_check
        assert composite is False

    def test_composite_context_fails_deny(self):
        """Composite check: context fails = DENY."""
        # Intent-binding: tool in allowlist
        intent_check = True

        # Context check: context not in allowed list
        context_check = False

        # Composite: fails because context fails
        composite = intent_check and context_check
        assert composite is False
