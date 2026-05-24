"""
FinanceFlow runner — launches all four agents for the full demo workflow.
Run: python runner.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AgentGuard-X"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents import (
    make_orchestrator_agent,
    make_research_agent,
    make_analyst_agent,
    make_report_agent,
)

BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
RESET = "\033[0m"


def run_full_workflow():
    print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{CYAN}  FinanceFlow × AgentGuard-X — Full Demo Workflow{RESET}")
    print(f"{BOLD}{CYAN}{'═'*60}{RESET}\n")

    research  = make_research_agent()
    analyst   = make_analyst_agent()
    report    = make_report_agent()

    steps = [
        (research, "Search for NVDA Q3 2024 financial results and recent market trends"),
        (analyst,  "Query internal database for NVDA key metrics and write a brief analysis"),
        (report,   "Write a one-paragraph Q3 NVDA investment summary report"),
        (report,   "Send the Q3 report to investment-team@financeflow.com with subject: Q3 NVDA Analysis"),
    ]

    for i, (agent, task) in enumerate(steps, 1):
        print(f"{BOLD}Step {i}/{len(steps)}: {task[:70]}{RESET}")
        try:
            result = agent.invoke({"input": task})
            output = result.get("output", result) if isinstance(result, dict) else result
            print(f"{GREEN}  Result: {str(output)[:120]}{RESET}\n")
        except Exception as e:
            print(f"  Blocked or errored: {e}\n")

    print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{GREEN}  Workflow complete.{RESET}")
    print(f"{BOLD}{CYAN}{'═'*60}{RESET}\n")


if __name__ == "__main__":
    run_full_workflow()
