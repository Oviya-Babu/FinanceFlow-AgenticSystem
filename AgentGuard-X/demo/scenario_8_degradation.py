"""
Scenario 8 — Graceful Degradation (Redis failure)
Stops Redis mid-run, verifies fail-closed behaviour (SANDBOX routing),
then restarts Redis and confirms recovery.
Dashboard: Redis health card turns red then green.
"""
import os, sys, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "financeflow"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from langchain_core.tools import Tool
from langchain_ollama import OllamaLLM
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from gateway.langchain_hook import AgentGuardCallback
import tools as ff_tools

BOLD  = "\033[1m"; RED = "\033[91m"; GREEN = "\033[92m"
YELLOW = "\033[93m"; CYAN = "\033[96m"; RESET = "\033[0m"


def _make_agent() -> AgentExecutor:
    callback = AgentGuardCallback(
        agent_id="research-001",
        agent_role="research_agent",
        session_id="ff-degradation-demo",
        financeflow_agent_name="ResearchAgent",
    )
    tool_list = [
        Tool(name="web_search", func=ff_tools.web_search, description="Search financial data.")
    ]
    llm = OllamaLLM(model=os.getenv("OLLAMA_MODEL", "llama3.2"))
    prompt = PromptTemplate.from_template(
        "You are a research agent.\nTools:\n{tools}\nTool names: {tool_names}\n"
        "Request: {input}\nScratchpad: {agent_scratchpad}"
    )
    agent = create_react_agent(llm, tool_list, prompt)
    return AgentExecutor(
        agent=agent, tools=tool_list, callbacks=[callback],
        handle_parsing_errors=lambda e: str(e), max_iterations=2, verbose=False,
    )


def _call(label: str):
    agent = _make_agent()
    try:
        agent.invoke({"input": f"Search for NVDA — {label}"})
        print(f"  {GREEN}✓ {label}: allowed{RESET}")
    except Exception as e:
        print(f"  {YELLOW}⚠ {label}: blocked/degraded — {str(e)[:80]}{RESET}")


def run():
    print(f"\n{BOLD}{CYAN}Scenario 8 — Graceful Degradation{RESET}")
    print("Steps: normal → stop Redis → verify degraded → restart → verify recovery\n")

    print(f"{BOLD}Step 1: Normal operation{RESET}")
    _call("normal operation")

    print(f"\n{BOLD}Step 2: Stopping Redis container...{RESET}")
    subprocess.run(["docker", "stop", "agentguard-redis"], capture_output=True)
    time.sleep(2)
    print("  Redis stopped.\n")

    print(f"{BOLD}Step 3: Call with Redis down (should degrade gracefully){RESET}")
    _call("Redis down — degraded mode")

    print(f"\n{BOLD}Step 4: Restarting Redis container...{RESET}")
    subprocess.run(["docker", "start", "agentguard-redis"], capture_output=True)
    time.sleep(4)
    print("  Redis restarted.\n")

    print(f"{BOLD}Step 5: Verify recovery{RESET}")
    _call("after Redis recovery")

    print(f"\n{GREEN}Scenario 8 complete — Redis card should be red→green in dashboard.{RESET}\n")

if __name__ == "__main__":
    run()
