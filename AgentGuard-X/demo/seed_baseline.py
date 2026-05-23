"""
Seed behavioral baselines for all 4 FinanceFlow agents into Redis.
Run once before any demo to give Stage 5 drift detection a reference point.

Usage: python demo/seed_baseline.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from session import redis_store

# 15 synthetic clean events per agent, one per minute back in time
_BASELINES = {
    "research_agent": [
        {"tool_name": "web_search",  "tool_input_raw": q, "score": 0.04, "verdict": "FAST_PATH"}
        for q in [
            "NVDA quarterly earnings Q3 2024",
            "TSLA market cap analysis",
            "SPY index performance Q3",
            "financial sector overview Q3 2024",
            "semiconductor market trends 2024",
            "NVDA revenue guidance fiscal 2025",
            "TSLA delivery numbers October 2024",
            "SPY sector rotation analysis",
            "NVDA datacentre demand forecast",
            "financial market weekly summary",
        ]
    ] + [
        {"tool_name": "read_file", "tool_input_raw": f, "score": 0.03, "verdict": "FAST_PATH"}
        for f in ["report.txt", "summary.txt", "data.csv", "notes.txt", "report.txt"]
    ],

    "analyst_agent": [
        {"tool_name": "query_internal_db", "tool_input_raw": q, "score": 0.03, "verdict": "FAST_PATH"}
        for q in [
            "SELECT revenue FROM financials WHERE ticker='NVDA'",
            "SELECT market_cap FROM stocks WHERE ticker='TSLA'",
            "SELECT * FROM portfolios LIMIT 10",
            "SELECT growth_rate FROM financials WHERE sector='tech'",
            "SELECT eps FROM financials WHERE ticker='NVDA' ORDER BY date DESC",
            "SELECT price, volume FROM stocks WHERE ticker='SPY'",
            "SELECT dividend FROM stocks WHERE yield > 0.03",
            "SELECT revenue, growth FROM financials WHERE quarter='Q3'",
            "SELECT beta FROM stocks WHERE market_cap > 1e12",
            "SELECT pe_ratio FROM stocks ORDER BY pe_ratio ASC LIMIT 20",
        ]
    ] + [
        {"tool_name": "write_report", "tool_input_raw": c, "score": 0.03, "verdict": "FAST_PATH"}
        for c in [
            "NVDA Q3 analysis: strong beat on revenue and EPS",
            "Portfolio rebalancing recommendation for Q4",
            "Sector rotation analysis: tech overweight maintained",
            "Risk assessment: low market volatility expected",
            "Monthly performance summary for investment committee",
        ]
    ],

    "report_agent": [
        {"tool_name": "write_report", "tool_input_raw": c, "score": 0.03, "verdict": "FAST_PATH"}
        for c in [
            "Q3 investment committee summary report",
            "NVDA position update — maintain overweight",
            "Quarterly risk assessment — all clear",
            "Monthly client newsletter draft",
            "Annual portfolio performance report",
            "Market outlook for Q4 2024",
            "ESG compliance report — no issues",
            "Trade execution summary October 2024",
        ]
    ] + [
        {"tool_name": "send_email", "tool_input_raw": e, "score": 0.03, "verdict": "FAST_PATH"}
        for e in [
            "investment-team@financeflow.com|Q3 Report|See attached",
            "investment-team@financeflow.com|Monthly Update|Markets stable",
            "investment-team@financeflow.com|Risk Alert|Low severity",
            "investment-team@financeflow.com|Earnings Summary|NVDA beat",
            "investment-team@financeflow.com|Portfolio Review|Q3 performance",
            "investment-team@financeflow.com|Compliance|Monthly clear",
            "investment-team@financeflow.com|Market Update|SPY +5.5% Q3",
        ]
    ],

    "orchestrator_agent": [
        {"tool_name": "spawn_agent", "tool_input_raw": t, "score": 0.04, "verdict": "FAST_PATH"}
        for t in [
            "research_agent|Analyse NVDA Q3 results",
            "analyst_agent|Query internal DB for Q3 metrics",
            "report_agent|Write quarterly investment summary",
            "research_agent|Search for semiconductor sector news",
            "analyst_agent|Generate risk assessment report",
            "report_agent|Send monthly newsletter",
            "research_agent|Fetch SPY performance data",
            "analyst_agent|Analyse portfolio allocation",
            "report_agent|Prepare board presentation",
            "research_agent|TSLA earnings analysis",
            "analyst_agent|DB query: top 10 holdings",
            "report_agent|ESG compliance draft",
            "research_agent|Macro economic overview Q4",
            "analyst_agent|Sector weighting review",
            "report_agent|Client update Q3",
        ]
    ],
}

_SESSIONS = {
    "ff-session-research":     "research_agent",
    "ff-session-analyst":      "analyst_agent",
    "ff-session-report":       "report_agent",
    "ff-session-orchestrator": "orchestrator_agent",
}


def seed():
    now = time.time()

    for role, events in _BASELINES.items():
        timestamped = []
        for i, ev in enumerate(events):
            ev = dict(ev, timestamp=now - (len(events) - i) * 60)
            timestamped.append(ev)
        redis_store.set_baseline(role, timestamped)
        print(f"  Baseline seeded: {role} ({len(timestamped)} events)")

    for session_id, role in _SESSIONS.items():
        events = _BASELINES[role]
        last5 = [dict(e, timestamp=now - (5 - i) * 60) for i, e in enumerate(events[-5:])]
        redis_store.init_session(session_id)
        for ev in last5:
            redis_store.append_to_session(session_id, ev)
        print(f"  Session hydrated: {session_id} (5 events)")

    print(
        "\nBaseline seeded: "
        + ", ".join(f"{r} ({len(e)})" for r, e in _BASELINES.items())
        + ". Session histories initialized."
    )


if __name__ == "__main__":
    seed()
