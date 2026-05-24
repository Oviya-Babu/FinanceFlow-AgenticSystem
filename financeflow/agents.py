"""
FinanceFlow demo agents — four LangChain agents using OllamaLLM,
each wrapped with AgentGuardCallback for runtime security interception.
"""
import os
import sys

# Add AgentGuard-X to path so callback can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AgentGuard-X"))

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import Tool
from langchain_ollama import OllamaLLM

from gateway.langchain_hook import AgentGuardCallback
import tools as ff_tools

_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
_OLLAMA_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _make_llm() -> OllamaLLM:
    return OllamaLLM(model=_OLLAMA_MODEL, base_url=_OLLAMA_URL)


def _react_prompt(role_desc: str) -> PromptTemplate:
    return PromptTemplate.from_template(
        f"You are a {role_desc}.\n\n"
        "Use the available tools to answer the following request.\n\n"
        "Tools:\n{tools}\n\n"
        "Tool names: {tool_names}\n\n"
        "Request: {input}\n\n"
        "Scratchpad: {agent_scratchpad}"
    )


# ─── OrchestratorAgent ────────────────────────────────────────────────────────
def make_orchestrator_agent(session_id: str = "ff-session-orchestrator") -> AgentExecutor:
    agent_id   = "orchestrator-001"
    agent_role = "orchestrator_agent"
    callback   = AgentGuardCallback(
        agent_id=agent_id,
        agent_role=agent_role,
        session_id=session_id,
        financeflow_agent_name="OrchestratorAgent",
    )
    tool_list = [
        Tool(name="spawn_agent", func=ff_tools.spawn_agent,
             description="Spawn a sub-agent to handle a delegated task. Input: 'agent_type|task'"),
    ]
    agent = create_react_agent(_make_llm(), tool_list, _react_prompt("FinanceFlow Orchestrator"))
    return AgentExecutor(
        agent=agent,
        tools=tool_list,
        callbacks=[callback],
        handle_parsing_errors=lambda e: str(e),
        max_iterations=3,
        verbose=False,
    )


# ─── ResearchAgent ────────────────────────────────────────────────────────────
def make_research_agent(session_id: str = "ff-session-research") -> AgentExecutor:
    agent_id   = "research-001"
    agent_role = "research_agent"
    callback   = AgentGuardCallback(
        agent_id=agent_id,
        agent_role=agent_role,
        session_id=session_id,
        financeflow_agent_name="ResearchAgent",
    )
    tool_list = [
        Tool(name="web_search", func=ff_tools.web_search,
             description="Search financial news and market data. Input: search query string."),
        Tool(name="read_pdf",   func=ff_tools.read_pdf,
             description="Read and summarize a PDF document. Input: file path."),
        Tool(name="read_file",  func=ff_tools.read_file,
             description="Read a local data file. Input: file path."),
    ]
    agent = create_react_agent(_make_llm(), tool_list, _react_prompt("FinanceFlow Research Agent"))
    return AgentExecutor(
        agent=agent,
        tools=tool_list,
        callbacks=[callback],
        handle_parsing_errors=lambda e: str(e),
        max_iterations=5,
        verbose=False,
    )


# ─── AnalystAgent ─────────────────────────────────────────────────────────────
def make_analyst_agent(session_id: str = "ff-session-analyst") -> AgentExecutor:
    agent_id   = "analyst-001"
    agent_role = "analyst_agent"
    callback   = AgentGuardCallback(
        agent_id=agent_id,
        agent_role=agent_role,
        session_id=session_id,
        financeflow_agent_name="AnalystAgent",
    )
    tool_list = [
        Tool(name="query_internal_db", func=ff_tools.query_internal_db,
             description="Query the internal financial database. Input: SQL-like query or description."),
        Tool(name="write_report",      func=ff_tools.write_report,
             description="Write a financial analysis report. Input: report content string."),
    ]
    agent = create_react_agent(_make_llm(), tool_list, _react_prompt("FinanceFlow Analyst"))
    return AgentExecutor(
        agent=agent,
        tools=tool_list,
        callbacks=[callback],
        handle_parsing_errors=lambda e: str(e),
        max_iterations=4,
        verbose=False,
    )


# ─── ReportAgent ─────────────────────────────────────────────────────────────
def make_report_agent(session_id: str = "ff-session-report") -> AgentExecutor:
    agent_id   = "report-001"
    agent_role = "report_agent"
    callback   = AgentGuardCallback(
        agent_id=agent_id,
        agent_role=agent_role,
        session_id=session_id,
        financeflow_agent_name="ReportAgent",
    )
    tool_list = [
        Tool(name="write_report", func=ff_tools.write_report,
             description="Write and save a report. Input: report content string."),
        Tool(name="send_email",   func=ff_tools.send_email,
             description="Send a report via email. Input: 'to|subject|body'"),
    ]
    agent = create_react_agent(_make_llm(), tool_list, _react_prompt("FinanceFlow Report Agent"))
    return AgentExecutor(
        agent=agent,
        tools=tool_list,
        callbacks=[callback],
        handle_parsing_errors=lambda e: str(e),
        max_iterations=3,
        verbose=False,
    )
