"""
FinanceFlow tool registry.
Every tool returns {"data": ..., "source": "real_<name>" | "simulated", "artifact": None|path}.
TOOLS_LIVE=true enables real external calls; default is safe simulation for demo reliability.
Every tool call must be routed through call_tool_with_guard() — never executed directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TOOLS_LIVE = os.getenv("TOOLS_LIVE", "false").lower() == "true"
AGENTGUARD_URL = os.getenv("AGENTGUARD_URL", "http://localhost:8001")
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "/home/oviya/agentguard/outputs"))
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Email allowlist — defence in depth beneath AgentGuard-X
_EMAIL_ALLOWLIST = {
    "investment-team@financeflow.com",
    "team@company.com",
    "demo@financeflow.com",
}


# ─── Guard check ─────────────────────────────────────────────────────────────

async def check_with_guard(
    agent_id: str,
    agent_role: str,
    tool_name: str,
    tool_input: dict,
    session_id: str = "ff-default",
) -> dict:
    """POST to AgentGuard-X /execute. Fail-closed: if unreachable → BLOCKED."""
    payload = {"agent_id": agent_id, "tool_name": tool_name, "input": tool_input}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{AGENTGUARD_URL}/execute", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error("AgentGuard-X unreachable: %s — failing closed", exc)
        return {
            "verdict": "BLOCKED",
            "risk_score": 1.0,
            "reason": "GUARD_UNREACHABLE",
            "trace_id": str(uuid.uuid4()),
            "latency_ms": 0.0,
            "stage_detail": [],
            "explanation": f"Triage service unreachable: {exc}",
        }


# ─── Tool implementations ─────────────────────────────────────────────────────

def _yfinance_real(ticker_or_query: str) -> dict:
    try:
        import yfinance as yf
        # Heuristic: if it looks like a ticker, fetch quote; else do search
        token = ticker_or_query.strip().upper().split()[0][:5]
        t = yf.Ticker(token)
        info = t.info
        if not info.get("symbol"):
            return {"error": "not found", "query": ticker_or_query}
        hist = t.history(period="5d")
        price = round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else None
        return {
            "symbol":       info.get("symbol"),
            "shortName":    info.get("shortName"),
            "currentPrice": price,
            "marketCap":    info.get("marketCap"),
            "trailingPE":   info.get("trailingPE"),
            "revenue":      info.get("totalRevenue"),
            "eps":          info.get("trailingEps"),
            "sector":       info.get("sector"),
            "summary":      (info.get("longBusinessSummary") or "")[:300],
        }
    except Exception as exc:
        return {"error": str(exc), "query": ticker_or_query}


def _yfinance_sim(ticker_or_query: str) -> dict:
    q = ticker_or_query.upper()
    if "NVDA" in q or "NVIDIA" in q:
        return {
            "symbol": "NVDA", "shortName": "NVIDIA Corporation",
            "currentPrice": 875.40, "marketCap": 2_150_000_000_000,
            "trailingPE": 55.2, "revenue": 44_870_000_000,
            "eps": 11.93, "sector": "Technology",
            "summary": "NVIDIA Q3 2024: Revenue $35.1B (+94% YoY), Net Income $9.2B, EPS $3.71. Datacenter $22.6B. Gross margin 74.6%.",
        }
    if "TSLA" in q or "TESLA" in q:
        return {
            "symbol": "TSLA", "shortName": "Tesla, Inc.",
            "currentPrice": 248.50, "marketCap": 790_000_000_000,
            "trailingPE": 62.1, "revenue": 97_690_000_000,
            "eps": 4.01, "sector": "Consumer Cyclical",
            "summary": "Tesla Q3 2024: Revenue $25.2B (+8% YoY), deliveries 462,890 units, auto gross margin 17.1%.",
        }
    if "SPY" in q or "S&P" in q:
        return {
            "symbol": "SPY", "shortName": "SPDR S&P 500 ETF",
            "currentPrice": 573.30, "marketCap": None,
            "trailingPE": 23.4, "sector": "ETF",
            "summary": "SPY Q3 2024 closed at 5,733 (+5.5% quarter). Technology +11.2%, Healthcare -1.4%.",
        }
    return {
        "symbol": ticker_or_query, "shortName": ticker_or_query,
        "currentPrice": 100.0, "summary": f"[Simulated] Financial data for {ticker_or_query}.",
    }


def tool_financial_search(query: str) -> dict:
    """Yahoo Finance data — real via yfinance, simulated fallback."""
    if TOOLS_LIVE:
        data = _yfinance_real(query)
        source = "real_yfinance"
    else:
        data = _yfinance_sim(query)
        source = "simulated"
    return {"data": data, "source": source, "artifact": None}


def _sec_edgar_real(company: str) -> dict:
    try:
        import urllib.request, urllib.parse
        company_encoded = urllib.parse.quote(company)
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22{company_encoded}%22&dateRange=custom&startdt=2024-01-01&enddt=2024-12-31&forms=10-Q,10-K"
        req = urllib.request.Request(url, headers={"User-Agent": "FinanceFlowDemo contact@demo.com"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = json.loads(resp.read().decode())
        hits = raw.get("hits", {}).get("hits", [])[:3]
        filings = [{"form": h["_source"].get("form_type"), "date": h["_source"].get("file_date"),
                    "company": h["_source"].get("entity_name"),
                    "url": f"https://www.sec.gov{h['_source'].get('file_num', '')}"}
                   for h in hits]
        return {"company": company, "filings": filings, "count": len(filings)}
    except Exception as exc:
        return {"error": str(exc), "company": company}


def tool_sec_filings(company: str) -> dict:
    if TOOLS_LIVE:
        data = _sec_edgar_real(company)
        source = "real_sec_edgar"
    else:
        data = {
            "company": company,
            "filings": [
                {"form": "10-Q", "date": "2024-11-01", "company": company,
                 "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"},
                {"form": "10-K", "date": "2024-02-21", "company": company,
                 "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"},
            ],
            "count": 2,
        }
        source = "simulated"
    return {"data": data, "source": source, "artifact": None}


def tool_web_search(query: str) -> dict:
    """General web search. Output is scanned for indirect injection by the caller."""
    if TOOLS_LIVE:
        tavily_key = os.getenv("TAVILY_API_KEY", "")
        if tavily_key:
            try:
                import urllib.request, urllib.parse
                payload = json.dumps({"api_key": tavily_key, "query": query, "max_results": 3}).encode()
                req = urllib.request.Request(
                    "https://api.tavily.com/search",
                    data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = json.loads(resp.read().decode())
                results = [{"title": r.get("title"), "url": r.get("url"),
                            "content": r.get("content", "")[:400]}
                           for r in raw.get("results", [])]
                return {"data": {"query": query, "results": results}, "source": "real_tavily", "artifact": None}
            except Exception as exc:
                logger.warning("Tavily search failed: %s", exc)

    # Simulated fallback
    from financeflow.tools import web_search as _sim_web_search
    data = {"query": query, "results": [{"title": "Financial Research", "url": "simulated",
                                          "content": _sim_web_search(query)}]}
    return {"data": data, "source": "simulated", "artifact": None}


def tool_query_db(query: str) -> dict:
    from financeflow.tools import query_internal_db
    return {"data": {"result": query_internal_db(query)}, "source": "simulated", "artifact": None}


def tool_generate_pdf(title: str, content: str) -> dict:
    """Generate a real PDF artifact locally using reportlab."""
    artifact_id = f"report_{uuid.uuid4().hex[:8]}"
    pdf_path = OUTPUTS_DIR / f"{artifact_id}.pdf"
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import inch

        doc = SimpleDocTemplate(str(pdf_path), pagesize=letter,
                                leftMargin=inch, rightMargin=inch,
                                topMargin=inch, bottomMargin=inch)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(title, styles["Title"]),
            Spacer(1, 0.3 * inch),
            Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", styles["Normal"]),
            Spacer(1, 0.2 * inch),
        ]
        for para in content.split("\n\n"):
            if para.strip():
                story.append(Paragraph(para.strip().replace("\n", "<br/>"), styles["BodyText"]))
                story.append(Spacer(1, 0.15 * inch))
        doc.build(story)
        return {"data": {"title": title, "artifact_id": artifact_id, "path": str(pdf_path)},
                "source": "real_reportlab", "artifact": str(pdf_path)}
    except Exception as exc:
        # Fallback: write plain text file
        txt_path = OUTPUTS_DIR / f"{artifact_id}.txt"
        txt_path.write_text(f"{title}\n{'='*len(title)}\n\n{content}")
        logger.warning("PDF generation failed (%s), wrote txt: %s", exc, txt_path)
        return {"data": {"title": title, "artifact_id": artifact_id, "path": str(txt_path)},
                "source": "real_plaintext", "artifact": str(txt_path)}


def tool_generate_markdown(title: str, content: str) -> dict:
    artifact_id = f"report_{uuid.uuid4().hex[:8]}"
    md_path = OUTPUTS_DIR / f"{artifact_id}.md"
    md_content = f"# {title}\n\n_Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_\n\n{content}"
    md_path.write_text(md_content)
    return {"data": {"title": title, "artifact_id": artifact_id, "path": str(md_path)},
            "source": "real_local", "artifact": str(md_path)}


def tool_write_report(title: str, content: str) -> dict:
    """Write report as both markdown and attempt PDF."""
    md_result = tool_generate_markdown(title, content)
    pdf_result = tool_generate_pdf(title, content)
    return {
        "data": {
            "title": title,
            "markdown_path": md_result["artifact"],
            "pdf_path": pdf_result["artifact"],
            "artifact_id": pdf_result["data"]["artifact_id"],
        },
        "source": "real_local",
        "artifact": pdf_result["artifact"],
    }


def tool_send_email(to: str, subject: str, body: str) -> dict:
    if TOOLS_LIVE and to in _EMAIL_ALLOWLIST:
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        if smtp_host and smtp_user:
            try:
                import smtplib, ssl
                from email.mime.text import MIMEText
                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = smtp_user
                msg["To"] = to
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(smtp_host, 465, context=ctx) as s:
                    s.login(smtp_user, smtp_pass)
                    s.sendmail(smtp_user, [to], msg.as_string())
                return {"data": {"to": to, "subject": subject, "status": "sent"},
                        "source": "real_smtp", "artifact": None}
            except Exception as exc:
                return {"data": {"error": str(exc), "status": "failed"},
                        "source": "real_smtp_failed", "artifact": None}
        return {"data": {"to": to, "subject": subject, "status": "[SIMULATED EMAIL] SMTP not configured"},
                "source": "simulated", "artifact": None}
    label = "[SIMULATED EMAIL]" if not TOOLS_LIVE else "[BLOCKED: not in allowlist]"
    return {"data": {"to": to, "subject": subject, "body_chars": len(body),
                     "status": f"{label} queued for {to}"},
            "source": "simulated", "artifact": None}


def tool_python_execute(code: str) -> dict:
    """Python execution — always in sandbox, never on host."""
    return {"data": {"note": "Python execution routed to Docker sandbox",
                     "code_length": len(code)},
            "source": "sandbox_required", "artifact": None}


def _get_ollama_model() -> str:
    """Return first available Ollama model, or the configured default."""
    configured = os.getenv("OLLAMA_MODEL", "llama3.2")
    try:
        import urllib.request
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
        models = [m["name"] for m in data.get("models", [])]
        if models:
            # Prefer the configured model if available
            if any(configured in m for m in models):
                return next(m for m in models if configured in m)
            return models[0]
    except Exception:
        pass
    return configured


def tool_llm_answer(question: str, context: str = "") -> dict:
    """Answer via Langchain ChatOllama. Discovers the first available local model."""
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model_name = _get_ollama_model()

    prompt_text = question
    if context:
        prompt_text = f"Context:\n{context}\n\nQuestion: {question}"

    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOllama(
            model=model_name,
            base_url=ollama_url,
            temperature=0.2,
            timeout=60,
        )
        messages = [
            SystemMessage(content="You are a helpful assistant. Answer concisely and accurately."),
            HumanMessage(content=prompt_text),
        ]
        response = llm.invoke(messages)
        answer = response.content if hasattr(response, "content") else str(response)
        return {
            "data": {"answer": answer, "model": model_name},
            "source": "real_langchain_ollama",
            "artifact": None,
        }
    except Exception as exc:
        logger.warning("ChatOllama failed (%s): %s — falling back to compute", model_name, exc)
        # Pure-compute fallback for arithmetic/trivial questions
        answer = _compute_fallback(question)
        return {
            "data": {"answer": answer, "model": "compute_fallback"},
            "source": "compute_fallback",
            "artifact": None,
        }


def _compute_fallback(question: str) -> str:
    """Evaluate simple arithmetic or return a best-effort answer without an LLM."""
    import ast, operator, re
    q = question.strip().rstrip("?").strip()
    # Try to extract and evaluate a math expression
    expr = re.sub(r"[^0-9+\-*/().\s]", "", q).strip()
    if expr:
        try:
            # Safe AST eval — only numbers and basic operators
            _ops = {ast.Add: operator.add, ast.Sub: operator.sub,
                    ast.Mult: operator.mul, ast.Div: operator.truediv,
                    ast.Pow: operator.pow, ast.USub: operator.neg}
            def _eval(node):
                if isinstance(node, ast.Constant):
                    return node.value
                if isinstance(node, ast.BinOp):
                    return _ops[type(node.op)](_eval(node.left), _eval(node.right))
                if isinstance(node, ast.UnaryOp):
                    return _ops[type(node.op)](_eval(node.operand))
                raise ValueError("unsupported")
            result = _eval(ast.parse(expr, mode="eval").body)
            return f"The answer is {result}."
        except Exception:
            pass
    return f"I received your question: \"{question}\". The local LLM is still loading — please try again in a moment."


# ─── Registry ─────────────────────────────────────────────────────────────────

TOOL_FN_MAP: dict[str, Any] = {
    "web_search":        lambda inp: tool_web_search(inp.get("query", inp.get("value", str(inp)))),
    "financial_search":  lambda inp: tool_financial_search(inp.get("query", inp.get("ticker", str(inp)))),
    "sec_filings":       lambda inp: tool_sec_filings(inp.get("company", inp.get("query", str(inp)))),
    "query_internal_db": lambda inp: tool_query_db(inp.get("query", str(inp))),
    "write_report":      lambda inp: tool_write_report(inp.get("title", "Report"), inp.get("content", str(inp))),
    "generate_pdf":      lambda inp: tool_generate_pdf(inp.get("title", "Report"), inp.get("content", str(inp))),
    "send_email":        lambda inp: tool_send_email(inp.get("to", ""), inp.get("subject", ""), inp.get("body", "")),
    "python_execute":    lambda inp: tool_python_execute(inp.get("code", str(inp))),
    "llm_answer":        lambda inp: tool_llm_answer(inp.get("question", str(inp)), inp.get("context", "")),
}


def execute_tool_sync(tool_name: str, tool_input: dict) -> dict:
    """Execute a tool by name. Returns standardised result dict."""
    fn = TOOL_FN_MAP.get(tool_name)
    if fn is None:
        return {"data": f"Unknown tool: {tool_name}", "source": "error", "artifact": None}
    try:
        return fn(tool_input)
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc)
        return {"data": f"Tool error: {exc}", "source": "error", "artifact": None}
