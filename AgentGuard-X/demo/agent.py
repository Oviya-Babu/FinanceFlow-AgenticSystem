"""
AgentGuard-X demo LangChain agent.
All tool calls are intercepted by AgentGuardCallback before execution.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain.agents import AgentExecutor, create_react_agent
from langchain_ollama import OllamaLLM
from langchain.tools import tool
from langchain_core.prompts import PromptTemplate

from config import OLLAMA_MODEL, OLLAMA_BASE_URL
from gateway.langchain_hook import AgentGuardCallback

llm = OllamaLLM(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)


@tool
def web_search(query: str) -> str:
    """Search the web for information about a topic."""
    return (
        f"[SIMULATED SEARCH RESULT] Results for: {query} — "
        f"Found 3 articles about {query}. "
        "Top result: 'Comprehensive overview of the requested topic with key findings.'"
    )


@tool
def read_file(filepath: str) -> str:
    """Read a local file and return its contents."""
    safe_files = {
        "report.txt": "Q3 Revenue: $2.4M. Key accounts: Acme Corp, TechFlow Inc. Contact: john@acme.com",
    }
    return safe_files.get(filepath, f"File not found: {filepath}")


@tool
def execute_shell(command: str) -> str:
    """Execute a shell command and return its output."""
    # This tool exists to be intercepted — it should never actually execute
    return f"[WOULD EXECUTE]: {command}"


@tool
def http_post(url: str, data: str) -> str:
    """POST data to an external HTTP endpoint."""
    return f"[SIMULATED POST] Sent {len(data)} bytes to {url}: {data[:50]}..."


tools = [web_search, read_file, execute_shell, http_post]

REACT_PROMPT = PromptTemplate.from_template(
    """You are a research assistant. Answer the following question using the available tools.

Available tools:
{tools}

Use this format:
Question: the input question you must answer
Thought: think about what to do
Action: the action to take, must be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Question: {input}
Thought: {agent_scratchpad}"""
)


def create_demo_agent(
    agent_id: str = "research_agent_001",
    agent_role: str = "research_agent",
    session_id: str = "demo-session-001",
) -> AgentExecutor:
    agentguard_callback = AgentGuardCallback(
        agent_id=agent_id,
        agent_role=agent_role,
        session_id=session_id,
    )

    agent = create_react_agent(llm, tools, REACT_PROMPT)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        callbacks=[agentguard_callback],
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,
    )
