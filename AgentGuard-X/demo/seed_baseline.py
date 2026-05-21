"""
Pre-seeds Redis with synthetic baseline profiles and a demo session history.
Run this once before demo/run_flows.py.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session import redis_store


def _make_event(tool_name: str, tool_input_raw: str, seconds_ago: float) -> dict:
    return {
        "tool_name": tool_name,
        "tool_input_raw": tool_input_raw,
        "timestamp": time.time() - seconds_ago,
        "score": 0.05,
    }


def seed_research_agent_baseline():
    events = [
        _make_event("web_search", "latest AI research papers 2024", 600),
        _make_event("web_search", "transformer architecture advances", 570),
        _make_event("read_file", "report.txt", 540),
        _make_event("web_search", "neural network training best practices", 510),
        _make_event("read_file", "report.txt", 480),
        _make_event("web_search", "OWASP LLM security guidelines", 450),
        _make_event("web_search", "AI safety research 2024", 420),
        _make_event("read_file", "report.txt", 390),
        _make_event("web_search", "machine learning deployment patterns", 360),
        _make_event("web_search", "agent security frameworks", 330),
        _make_event("read_file", "report.txt", 300),
        _make_event("web_search", "LangChain security best practices", 270),
        _make_event("web_search", "retrieval augmented generation security", 240),
        _make_event("read_file", "report.txt", 210),
        _make_event("web_search", "AI agent monitoring systems", 180),
    ]
    redis_store.set_baseline("research_agent", events)
    print(f"[seed] research_agent baseline: {len(events)} events")


def seed_data_agent_baseline():
    events = [
        _make_event("read_file", "data/records.csv", 600),
        _make_event("http_post", "http://internal-api.corp/ingest", 570),
        _make_event("read_file", "data/config.json", 540),
        _make_event("http_post", "http://internal-api.corp/update", 510),
        _make_event("read_file", "data/records.csv", 480),
        _make_event("http_post", "http://internal-api.corp/ingest", 450),
        _make_event("read_file", "data/schema.json", 420),
        _make_event("http_post", "http://internal-api.corp/validate", 390),
        _make_event("read_file", "data/records.csv", 360),
        _make_event("http_post", "http://internal-api.corp/ingest", 330),
        _make_event("read_file", "data/config.json", 300),
        _make_event("http_post", "http://internal-api.corp/update", 270),
        _make_event("read_file", "data/records.csv", 240),
        _make_event("http_post", "http://internal-api.corp/ingest", 210),
        _make_event("read_file", "data/schema.json", 180),
    ]
    redis_store.set_baseline("data_agent", events)
    print(f"[seed] data_agent baseline: {len(events)} events")


def seed_admin_agent_baseline():
    events = [
        _make_event("web_search", "system status dashboard", 600),
        _make_event("read_file", "config/system.yaml", 560),
        _make_event("execute_shell", "systemctl status nginx", 520),
        _make_event("web_search", "deployment checklist 2024", 480),
        _make_event("read_file", "logs/access.log", 440),
        _make_event("http_post", "http://internal-api.corp/admin/update", 400),
        _make_event("execute_shell", "df -h", 360),
        _make_event("web_search", "kubernetes pod status", 320),
        _make_event("read_file", "config/nginx.conf", 280),
        _make_event("execute_shell", "ps aux | head -20", 240),
    ]
    redis_store.set_baseline("admin_agent", events)
    print(f"[seed] admin_agent baseline: {len(events)} events")


def seed_demo_session():
    """Seed 8 clean prior requests for demo-session-001 (research_agent_001)."""
    import uuid
    events = [
        _make_event("web_search", "AI research papers machine learning", 120),
        _make_event("web_search", "neural networks deep learning survey", 110),
        _make_event("read_file", "report.txt", 100),
        _make_event("web_search", "transformer models attention mechanism", 90),
        _make_event("read_file", "report.txt", 80),
        _make_event("web_search", "AI safety alignment research", 70),
        _make_event("web_search", "reinforcement learning from human feedback", 60),
        _make_event("read_file", "report.txt", 50),
    ]
    redis_store.init_session("demo-session-001")
    for event in events:
        redis_store.append_to_session("demo-session-001", event)
    print(f"[seed] demo-session-001: {len(events)} events")


if __name__ == "__main__":
    print("Seeding AgentGuard-X Redis baseline data...")
    seed_research_agent_baseline()
    seed_data_agent_baseline()
    seed_admin_agent_baseline()
    seed_demo_session()
    print("Seeding complete.")
