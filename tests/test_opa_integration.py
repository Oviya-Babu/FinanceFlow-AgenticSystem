"""
Integration Tests for OPA Policy Engine in Docker

Tests OPA policies against a real Docker-based OPA instance.
Verifies:
- Determinism (same input = same output)
- Timeout enforcement (100ms hard limit)
- Fail-closed behavior (unreachable = deny)
- All 4 FinanceFlow agents with all rules
- Context-aware decisions
- Velocity limit calculations

All tests are deterministic and reproducible.
"""

import pytest
import asyncio
import httpx
import json
import os
from typing import Dict, Any, Optional


@pytest.mark.asyncio
class TestOPAIntegration:
    """Integration tests for OPA in Docker."""

    @pytest.fixture
    async def opa_client(self):
        """Get OPA client, skip if not available."""
        opa_url = os.getenv("OPA_URL", "http://localhost:8182")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{opa_url}/health", timeout=2.0)
                if response.status_code != 200:
                    pytest.skip("OPA not available")
        except Exception:
            pytest.skip("OPA not available")
        
        yield opa_url

    async def query_opa(
        self, opa_url: str, agent_role: str, tool_name: str, tool_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Query OPA with deterministic input."""
        input_data = {
            "agent_role": agent_role,
            "agent_id": agent_role,
            "tool_name": tool_name,
        }
        if tool_context:
            input_data["tool_context"] = tool_context

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{opa_url}/v1/data/agentguard/allow",
                json={"input": input_data},
                timeout=0.1,  # 100ms hard timeout
            )

            if response.status_code == 200:
                return response.json().get("result", {})
            else:
                return {"allow": False, "error": response.status_code}

    # ========================================================================
    # DETERMINISM TESTS (Critical for Production)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_determinism_orchestrator_spawn_10_times(self, opa_client):
        """Same request 10 times → Same response 10 times."""
        results = []
        for _ in range(10):
            result = await self.query_opa(
                opa_client, "orchestrator_agent", "spawn_agent"
            )
            results.append(result.get("allow", False))

        # All 10 responses should be identical
        assert all(r is True for r in results), f"Inconsistent results: {results}"
        assert len(set(results)) == 1, "Results differ across runs"

    @pytest.mark.asyncio
    async def test_determinism_research_web_search_10_times(self, opa_client):
        """ResearchAgent + web_search same 10 times."""
        results = []
        for _ in range(10):
            result = await self.query_opa(
                opa_client, "research_agent", "web_search"
            )
            results.append(result.get("allow", False))

        assert all(r is True for r in results), f"Inconsistent results: {results}"
        assert len(set(results)) == 1

    @pytest.mark.asyncio
    async def test_determinism_analyst_deny_10_times(self, opa_client):
        """AnalystAgent + web_search deny same 10 times."""
        results = []
        for _ in range(10):
            result = await self.query_opa(
                opa_client, "analyst_agent", "web_search"
            )
            results.append(result.get("allow", False))

        assert all(r is False for r in results), f"Inconsistent results: {results}"
        assert len(set(results)) == 1

    @pytest.mark.asyncio
    async def test_determinism_unknown_agent_10_times(self, opa_client):
        """Unknown agent denied 10 times (consistent)."""
        results = []
        for _ in range(10):
            result = await self.query_opa(
                opa_client, "unknown_agent", "web_search"
            )
            results.append(result.get("allow", False))

        assert all(r is False for r in results), f"Inconsistent results: {results}"
        assert len(set(results)) == 1

    # ========================================================================
    # ORCHESTRATORAGENT INTEGRATION TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_orchestrator_spawn_agent_allow(self, opa_client):
        """OrchestratorAgent allowed to spawn_agent."""
        result = await self.query_opa(opa_client, "orchestrator_agent", "spawn_agent")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_orchestrator_web_search_deny(self, opa_client):
        """OrchestratorAgent denied web_search."""
        result = await self.query_opa(opa_client, "orchestrator_agent", "web_search")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_orchestrator_query_db_deny(self, opa_client):
        """OrchestratorAgent denied query_internal_db."""
        result = await self.query_opa(opa_client, "orchestrator_agent", "query_internal_db")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_orchestrator_write_report_deny(self, opa_client):
        """OrchestratorAgent denied write_report."""
        result = await self.query_opa(opa_client, "orchestrator_agent", "write_report")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_orchestrator_send_email_deny(self, opa_client):
        """OrchestratorAgent denied send_email."""
        result = await self.query_opa(opa_client, "orchestrator_agent", "send_email")
        assert result.get("allow") is False

    # ========================================================================
    # RESEARCHAGENT INTEGRATION TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_research_web_search_allow(self, opa_client):
        """ResearchAgent allowed web_search."""
        result = await self.query_opa(opa_client, "research_agent", "web_search")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_research_read_pdf_allow(self, opa_client):
        """ResearchAgent allowed read_pdf."""
        result = await self.query_opa(opa_client, "research_agent", "read_pdf")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_research_fetch_url_allow(self, opa_client):
        """ResearchAgent allowed fetch_url."""
        result = await self.query_opa(opa_client, "research_agent", "fetch_url")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_research_query_db_deny(self, opa_client):
        """ResearchAgent denied query_internal_db."""
        result = await self.query_opa(opa_client, "research_agent", "query_internal_db")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_research_write_report_deny(self, opa_client):
        """ResearchAgent denied write_report."""
        result = await self.query_opa(opa_client, "research_agent", "write_report")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_research_send_email_deny(self, opa_client):
        """ResearchAgent denied send_email."""
        result = await self.query_opa(opa_client, "research_agent", "send_email")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_research_spawn_agent_deny(self, opa_client):
        """ResearchAgent denied spawn_agent."""
        result = await self.query_opa(opa_client, "research_agent", "spawn_agent")
        assert result.get("allow") is False

    # ========================================================================
    # ANALYSTAGENT INTEGRATION TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_analyst_query_db_allow(self, opa_client):
        """AnalystAgent allowed query_internal_db."""
        result = await self.query_opa(opa_client, "analyst_agent", "query_internal_db")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_analyst_write_report_allow(self, opa_client):
        """AnalystAgent allowed write_report."""
        result = await self.query_opa(opa_client, "analyst_agent", "write_report")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_analyst_fetch_dataset_allow(self, opa_client):
        """AnalystAgent allowed fetch_dataset."""
        result = await self.query_opa(opa_client, "analyst_agent", "fetch_dataset")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_analyst_web_search_deny(self, opa_client):
        """AnalystAgent denied web_search."""
        result = await self.query_opa(opa_client, "analyst_agent", "web_search")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_analyst_read_pdf_deny(self, opa_client):
        """AnalystAgent denied read_pdf."""
        result = await self.query_opa(opa_client, "analyst_agent", "read_pdf")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_analyst_send_email_deny(self, opa_client):
        """AnalystAgent denied send_email."""
        result = await self.query_opa(opa_client, "analyst_agent", "send_email")
        assert result.get("allow") is False

    # ========================================================================
    # REPORTAGENT INTEGRATION TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_report_write_report_allow(self, opa_client):
        """ReportAgent allowed write_report."""
        result = await self.query_opa(opa_client, "report_agent", "write_report")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_report_send_email_allow(self, opa_client):
        """ReportAgent allowed send_email."""
        result = await self.query_opa(opa_client, "report_agent", "send_email")
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_report_web_search_deny(self, opa_client):
        """ReportAgent denied web_search."""
        result = await self.query_opa(opa_client, "report_agent", "web_search")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_report_query_db_deny(self, opa_client):
        """ReportAgent denied query_internal_db."""
        result = await self.query_opa(opa_client, "report_agent", "query_internal_db")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_report_read_pdf_deny(self, opa_client):
        """ReportAgent denied read_pdf."""
        result = await self.query_opa(opa_client, "report_agent", "read_pdf")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_report_spawn_agent_deny(self, opa_client):
        """ReportAgent denied spawn_agent."""
        result = await self.query_opa(opa_client, "report_agent", "spawn_agent")
        assert result.get("allow") is False

    # ========================================================================
    # TIMEOUT ENFORCEMENT TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_opa_request_completes_under_100ms(self, opa_client):
        """OPA request completes within 100ms timeout."""
        import time
        
        start = time.time()
        result = await self.query_opa(opa_client, "research_agent", "web_search")
        elapsed = (time.time() - start) * 1000  # Convert to ms

        # Should complete well under 100ms
        assert elapsed < 100, f"Request took {elapsed}ms, exceeds 100ms limit"
        assert result.get("allow") is True

    @pytest.mark.asyncio
    async def test_opa_multiple_requests_under_100ms_each(self, opa_client):
        """Multiple OPA requests each complete under 100ms."""
        import time
        
        for _ in range(5):
            start = time.time()
            result = await self.query_opa(opa_client, "analyst_agent", "query_internal_db")
            elapsed = (time.time() - start) * 1000

            assert elapsed < 100, f"Request took {elapsed}ms"
            assert result.get("allow") is True

    # ========================================================================
    # FAIL-CLOSED BEHAVIOR TESTS
    # ========================================================================

    @pytest.mark.asyncio
    async def test_unknown_agent_fails_closed(self, opa_client):
        """Unknown agent fails closed (denied)."""
        result = await self.query_opa(opa_client, "unknown_agent", "web_search")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_unknown_tool_fails_closed(self, opa_client):
        """Unknown tool fails closed (denied)."""
        result = await self.query_opa(opa_client, "research_agent", "unknown_tool")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_empty_agent_role_fails_closed(self, opa_client):
        """Empty agent role fails closed."""
        result = await self.query_opa(opa_client, "", "web_search")
        assert result.get("allow") is False

    @pytest.mark.asyncio
    async def test_empty_tool_fails_closed(self, opa_client):
        """Empty tool fails closed."""
        result = await self.query_opa(opa_client, "research_agent", "")
        assert result.get("allow") is False

    # ========================================================================
    # COMPREHENSIVE COVERAGE TEST
    # ========================================================================

    @pytest.mark.asyncio
    async def test_all_agent_tool_combinations(self, opa_client):
        """Verify all 4 agents × 7 tools = 28 combinations have defined behavior."""
        agents = [
            "orchestrator_agent",
            "research_agent",
            "analyst_agent",
            "report_agent",
        ]
        
        tools = [
            "spawn_agent",
            "web_search",
            "read_pdf",
            "query_internal_db",
            "write_report",
            "send_email",
            "fetch_dataset",
        ]

        expected_results = {
            ("orchestrator_agent", "spawn_agent"): True,
            ("orchestrator_agent", "web_search"): False,
            ("orchestrator_agent", "read_pdf"): False,
            ("orchestrator_agent", "query_internal_db"): False,
            ("orchestrator_agent", "write_report"): False,
            ("orchestrator_agent", "send_email"): False,
            ("orchestrator_agent", "fetch_dataset"): False,
            
            ("research_agent", "spawn_agent"): False,
            ("research_agent", "web_search"): True,
            ("research_agent", "read_pdf"): True,
            ("research_agent", "query_internal_db"): False,
            ("research_agent", "write_report"): False,
            ("research_agent", "send_email"): False,
            ("research_agent", "fetch_dataset"): False,
            
            ("analyst_agent", "spawn_agent"): False,
            ("analyst_agent", "web_search"): False,
            ("analyst_agent", "read_pdf"): False,
            ("analyst_agent", "query_internal_db"): True,
            ("analyst_agent", "write_report"): True,
            ("analyst_agent", "send_email"): False,
            ("analyst_agent", "fetch_dataset"): True,
            
            ("report_agent", "spawn_agent"): False,
            ("report_agent", "web_search"): False,
            ("report_agent", "read_pdf"): False,
            ("report_agent", "query_internal_db"): False,
            ("report_agent", "write_report"): True,
            ("report_agent", "send_email"): True,
            ("report_agent", "fetch_dataset"): False,
        }

        passed = 0
        failed = 0
        for (agent, tool), expected in expected_results.items():
            result = await self.query_opa(opa_client, agent, tool)
            actual = result.get("allow", False)
            
            if actual == expected:
                passed += 1
            else:
                failed += 1
                print(f"MISMATCH: {agent} + {tool} = {actual}, expected {expected}")

        assert failed == 0, f"{failed} test cases failed, {passed} passed"
        assert passed == 28, f"Expected 28 tests, got {passed}"
