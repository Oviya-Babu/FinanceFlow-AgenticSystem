"""
Scenario 7 — Rate Limiting
20 concurrent research_agent calls. OPA rate limit is 30/min, but rapid burst
should trigger drift Stage 5 temporal anomaly. Expect most blocked after ~5-10.
Dashboard: spike in timeline chart, orange/red events.

NOTE: Creates separate agent instances per thread (LangChain AgentExecutor is not thread-safe).
"""
import os, sys, threading, time
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

BOLD = "\033[1m"; RED = "\033[91m"; GREEN = "\033[92m"; CYAN = "\033[96m"; RESET = "\033[0m"


def _make_agent(thread_id: int) -> AgentExecutor:
    callback = AgentGuardCallback(
        agent_id="research-001",
        agent_role="research_agent",
        session_id=f"ff-rate-{thread_id}",
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


def run():
    print(f"\n{BOLD}{CYAN}Scenario 7 — Rate Limiting (20 concurrent calls){RESET}")
    print("Expected: first few FAST_PATH, remaining drift-elevated SANDBOX/BLOCK\n")

    results = []
    lock = threading.Lock()

    def make_call(i: int):
        agent = _make_agent(i)
        try:
            agent.invoke({"input": f"Search for tech news update {i}"})
            with lock:
                results.append(("ALLOWED", i))
        except Exception as e:
            with lock:
                results.append(("BLOCKED", i, str(e)[:60]))

    threads = [threading.Thread(target=make_call, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed = sum(1 for r in results if r[0] == "ALLOWED")
    blocked = sum(1 for r in results if r[0] == "BLOCKED")
    print(f"\n  {GREEN}Allowed: {allowed}{RESET}  |  {RED}Blocked: {blocked}{RESET}\n")
    print(f"{CYAN}Scenario 7 complete — observe timeline spike in dashboard.{RESET}\n")

if __name__ == "__main__":
    run()
