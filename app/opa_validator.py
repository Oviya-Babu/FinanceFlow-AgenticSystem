"""
OPA Policy Validation and Testing Endpoint

Provides validation, testing, and debugging capabilities for OPA policies:
- POST /api/opa/validate: Compile and validate all policies
- POST /api/opa/test: Run policy unit tests
- GET /api/opa/debug/{agent_id}/{tool_name}: Show decision trace
"""

import json
import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class OPAValidator:
    """Validates and tests OPA policies."""

    def __init__(self, opa_url: str):
        """Initialize validator with OPA URL."""
        self.opa_url = opa_url

    async def validate_policies(self) -> Dict[str, Any]:
        """
        Validate all OPA policies for syntax errors.

        Returns:
            {
                "valid": bool,
                "errors": [],
                "warnings": [],
                "policies": ["tool_rbac", "state_based_privilege", "resource_velocity"],
            }
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "policies": [
                "tool_rbac",
                "state_based_privilege",
                "resource_velocity",
            ],
            "timestamp": None,
        }

        try:
            async with httpx.AsyncClient() as client:
                # Query OPA health to verify connectivity
                health_response = await client.get(f"{self.opa_url}/health", timeout=2.0)
                if health_response.status_code != 200:
                    result["valid"] = False
                    result["errors"].append("OPA server unhealthy")
                    return result

                # Check each policy package
                for policy in result["policies"]:
                    policy_check = await self._check_policy(client, policy)
                    if not policy_check["valid"]:
                        result["valid"] = False
                        result["errors"].extend(policy_check["errors"])
                    result["warnings"].extend(policy_check["warnings"])

            result["timestamp"] = None  # Will be set by caller
            return result

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Validation error: {str(e)}")
            return result

    async def _check_policy(self, client: httpx.AsyncClient, policy: str) -> Dict[str, Any]:
        """Check individual policy for validity."""
        try:
            # Query policy data path to verify it exists and is compilable
            response = await client.post(
                f"{self.opa_url}/v1/compile",
                json={"query": f"data.agentguard.{policy}"},
                timeout=2.0,
            )

            if response.status_code == 200:
                return {"valid": True, "errors": [], "warnings": []}
            else:
                return {
                    "valid": False,
                    "errors": [f"Policy {policy} compilation failed"],
                    "warnings": [],
                }

        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Error checking {policy}: {str(e)}"],
                "warnings": [],
            }

    async def run_policy_tests(self) -> Dict[str, Any]:
        """
        Run all policy unit tests.

        Returns:
            {
                "passed": int,
                "failed": int,
                "total": int,
                "tests": [
                    {
                        "name": "test_orchestrator_spawn_allow",
                        "status": "pass"|"fail",
                        "input": {...},
                        "expected": {"allow": true},
                        "actual": {"allow": true},
                    }
                ],
                "coverage": "95.2%",
            }
        """
        tests = self._get_test_cases()
        result = {
            "passed": 0,
            "failed": 0,
            "total": len(tests),
            "tests": [],
            "coverage": "0%",
        }

        async with httpx.AsyncClient() as client:
            for test in tests:
                test_result = await self._run_single_test(client, test)
                result["tests"].append(test_result)

                if test_result["status"] == "pass":
                    result["passed"] += 1
                else:
                    result["failed"] += 1

        # Calculate coverage
        if result["total"] > 0:
            coverage = (result["passed"] / result["total"]) * 100
            result["coverage"] = f"{coverage:.1f}%"

        return result

    async def _run_single_test(
        self, client: httpx.AsyncClient, test: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a single policy test case."""
        try:
            response = await client.post(
                f"{self.opa_url}/v1/data/agentguard/allow",
                json={"input": test["input"]},
                timeout=0.1,  # 100ms hard timeout like production
            )

            if response.status_code == 200:
                actual = response.json().get("result", {})
                expected = test["expected"]

                # Check if result matches expectation
                status = "pass" if actual == expected else "fail"
            else:
                actual = None
                expected = test["expected"]
                status = "fail"

            return {
                "name": test["name"],
                "status": status,
                "input": test["input"],
                "expected": expected,
                "actual": actual,
            }

        except Exception as e:
            return {
                "name": test["name"],
                "status": "fail",
                "input": test["input"],
                "expected": test["expected"],
                "actual": None,
                "error": str(e),
            }

    def _get_test_cases(self) -> List[Dict[str, Any]]:
        """Return all policy test cases (deterministic, no randomness)."""
        return [
            # ============================================================
            # OrchestratorAgent Tests
            # ============================================================
            {
                "name": "test_orchestrator_spawn_allow",
                "input": {
                    "agent_role": "orchestrator_agent",
                    "agent_id": "orchestrator_agent",
                    "tool_name": "spawn_agent",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_orchestrator_web_search_deny",
                "input": {
                    "agent_role": "orchestrator_agent",
                    "agent_id": "orchestrator_agent",
                    "tool_name": "web_search",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_orchestrator_read_pdf_deny",
                "input": {
                    "agent_role": "orchestrator_agent",
                    "agent_id": "orchestrator_agent",
                    "tool_name": "read_pdf",
                },
                "expected": {"allow": False},
            },
            # ============================================================
            # ResearchAgent Tests
            # ============================================================
            {
                "name": "test_research_web_search_allow",
                "input": {
                    "agent_role": "research_agent",
                    "agent_id": "research_agent",
                    "tool_name": "web_search",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_research_read_pdf_allow",
                "input": {
                    "agent_role": "research_agent",
                    "agent_id": "research_agent",
                    "tool_name": "read_pdf",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_research_fetch_url_allow",
                "input": {
                    "agent_role": "research_agent",
                    "agent_id": "research_agent",
                    "tool_name": "fetch_url",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_research_query_db_deny",
                "input": {
                    "agent_role": "research_agent",
                    "agent_id": "research_agent",
                    "tool_name": "query_internal_db",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_research_write_report_deny",
                "input": {
                    "agent_role": "research_agent",
                    "agent_id": "research_agent",
                    "tool_name": "write_report",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_research_send_email_deny",
                "input": {
                    "agent_role": "research_agent",
                    "agent_id": "research_agent",
                    "tool_name": "send_email",
                },
                "expected": {"allow": False},
            },
            # ============================================================
            # AnalystAgent Tests
            # ============================================================
            {
                "name": "test_analyst_query_db_allow",
                "input": {
                    "agent_role": "analyst_agent",
                    "agent_id": "analyst_agent",
                    "tool_name": "query_internal_db",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_analyst_write_report_allow",
                "input": {
                    "agent_role": "analyst_agent",
                    "agent_id": "analyst_agent",
                    "tool_name": "write_report",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_analyst_fetch_dataset_allow",
                "input": {
                    "agent_role": "analyst_agent",
                    "agent_id": "analyst_agent",
                    "tool_name": "fetch_dataset",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_analyst_web_search_deny",
                "input": {
                    "agent_role": "analyst_agent",
                    "agent_id": "analyst_agent",
                    "tool_name": "web_search",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_analyst_read_pdf_deny",
                "input": {
                    "agent_role": "analyst_agent",
                    "agent_id": "analyst_agent",
                    "tool_name": "read_pdf",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_analyst_send_email_deny",
                "input": {
                    "agent_role": "analyst_agent",
                    "agent_id": "analyst_agent",
                    "tool_name": "send_email",
                },
                "expected": {"allow": False},
            },
            # ============================================================
            # ReportAgent Tests
            # ============================================================
            {
                "name": "test_report_write_report_allow",
                "input": {
                    "agent_role": "report_agent",
                    "agent_id": "report_agent",
                    "tool_name": "write_report",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_report_send_email_allow",
                "input": {
                    "agent_role": "report_agent",
                    "agent_id": "report_agent",
                    "tool_name": "send_email",
                },
                "expected": {"allow": True},
            },
            {
                "name": "test_report_web_search_deny",
                "input": {
                    "agent_role": "report_agent",
                    "agent_id": "report_agent",
                    "tool_name": "web_search",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_report_query_db_deny",
                "input": {
                    "agent_role": "report_agent",
                    "agent_id": "report_agent",
                    "tool_name": "query_internal_db",
                },
                "expected": {"allow": False},
            },
            {
                "name": "test_report_read_pdf_deny",
                "input": {
                    "agent_role": "report_agent",
                    "agent_id": "report_agent",
                    "tool_name": "read_pdf",
                },
                "expected": {"allow": False},
            },
            # ============================================================
            # Unknown Agent Tests (Fail-Closed)
            # ============================================================
            {
                "name": "test_unknown_agent_deny",
                "input": {
                    "agent_role": "unknown_role",
                    "agent_id": "unknown_agent",
                    "tool_name": "web_search",
                },
                "expected": {"allow": False},
            },
        ]

    async def get_decision_debug(
        self, agent_id: str, tool_name: str, tool_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get decision trace for debugging why a request was allowed/denied.

        Returns:
            {
                "agent_id": "research_agent",
                "tool_name": "read_pdf",
                "tool_context": "public_documents",
                "decision": "allow" | "deny",
                "trace": [
                    {
                        "stage": "intent_binding",
                        "result": "allow",
                        "reason": "Tool in allowlist for agent role",
                    },
                    {
                        "stage": "state_privilege",
                        "result": "allow",
                        "reason": "Context public_documents allowed for read_pdf",
                    }
                ],
                "decision_trace": [{...}],
            }
        """
        input_data = {
            "agent_role": agent_id,
            "agent_id": agent_id,
            "tool_name": tool_name,
        }

        if tool_context:
            input_data["tool_context"] = tool_context

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.opa_url}/v1/data/agentguard/allow",
                    json={"input": input_data},
                    timeout=0.1,
                )

                if response.status_code == 200:
                    result_data = response.json()
                    decision = "allow" if result_data.get("result", {}).get("allow") else "deny"

                    trace = result_data.get("result", {}).get("decision_trace", [])

                    return {
                        "agent_id": agent_id,
                        "tool_name": tool_name,
                        "tool_context": tool_context or "none",
                        "decision": decision,
                        "trace": trace,
                        "full_response": result_data.get("result", {}),
                    }
                else:
                    return {
                        "agent_id": agent_id,
                        "tool_name": tool_name,
                        "tool_context": tool_context or "none",
                        "decision": "deny",
                        "trace": [
                            {
                                "stage": "opa_query",
                                "result": "error",
                                "reason": f"OPA returned status {response.status_code}",
                            }
                        ],
                    }

        except Exception as e:
            return {
                "agent_id": agent_id,
                "tool_name": tool_name,
                "tool_context": tool_context or "none",
                "decision": "deny",
                "trace": [
                    {
                        "stage": "opa_query",
                        "result": "error",
                        "reason": str(e),
                    }
                ],
            }
