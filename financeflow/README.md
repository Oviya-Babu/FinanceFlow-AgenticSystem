# FinanceFlow Enterprise Agentic Platform

## Overview

FinanceFlow is a **production-grade autonomous AI platform** for enterprise financial research, analysis, and reporting. It implements a realistic multi-agent architecture designed to be integrated with AgentGuard-X security mesh later.

### Key Characteristics

✅ **Real Autonomous Agents** - Not mocked, actual LangChain agents with dynamic reasoning  
✅ **Async-First Architecture** - Fully asynchronous FastAPI + asyncio runtime  
✅ **Observable by Design** - OpenTelemetry tracing, Prometheus metrics, structured logging  
✅ **Integration-Ready** - Clean interception points for external security mesh  
✅ **Vulnerability by Design** - Realistic attack surface for security testing  

---

## Architecture

### Multi-Agent System

```
User Request
    ↓
[OrchestratorAgent] - Decomposes tasks, coordinates workflow
    ↓
    ├→ [ResearchAgent] - Web search, document analysis
    ├→ [AnalystAgent] - Financial analysis, modeling
    └→ [ReportAgent] - Report generation, delivery
    ↓
Response
```

### Agents

**OrchestratorAgent**
- Receives user requests
- Dynamically decomposes tasks
- Coordinates sub-agent execution
- Manages workflow state

**ResearchAgent**
- Web search for financial news
- Webpage scraping
- PDF document analysis
- Document summarization

**AnalystAgent**
- Internal database queries
- Financial modeling (DCF, valuation)
- Trend analysis
- Report generation

**ReportAgent**
- Report formatting
- PDF export
- Email delivery (dangerous operation)
- Publication management

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | FastAPI (async) |
| **Agent Runtime** | LangChain |
| **LLM Inference** | Ollama (llama3.2:3b or phi3:mini) |
| **Memory Layer** | Redis |
| **Enterprise Data** | SQLite |
| **Observability** | OpenTelemetry + Jaeger + Prometheus |
| **Logging** | Structured JSON logging |
| **Language** | Python 3.11+ |

---

## Installation

### Prerequisites

- Python 3.11+
- Redis server running on localhost:6379
- Ollama running on localhost:11434
- (Optional) Jaeger for distributed tracing
- (Optional) Prometheus for metrics

### Setup Steps

1. **Clone and navigate to project:**
```bash
cd financeflow
```

2. **Create virtual environment:**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Create .env file:**
```bash
cp .env.example .env
```

Edit `.env` as needed for your environment.

5. **Initialize Ollama:**
```bash
# Start Ollama service
ollama serve

# In another terminal, pull model
ollama pull llama3.2:3b
# OR
ollama pull phi3:mini
```

6. **Start Redis:**

## Running the Platform

### Start FinanceFlow Server

**Flow:**
1. OrchestratorAgent receives request
2. Delegates web research to ResearchAgent
3. AnalystAgent analyzes internal metrics
4. ReportAgent synthesizes executive summary
5. Results delivered to stakeholder


## Integration with AgentGuard-X

FinanceFlow is designed to be protected by AgentGuard-X security mesh with these integration points:

### Interception Hooks

- **Before Tool Execution** - Inspect tool and parameters
- **After Tool Execution** - Analyze output
- **Inter-Agent Communication** - Monitor message exchange
- **External API Calls** - Intercept HTTP traffic

### Observability Integration

- **Trace Propagation** - traceparent headers in requests
- **Correlation IDs** - Request tracking
- **Execution Metadata** - Tool execution details

### Proxy Compatibility

Compatible with:
- **mitmproxy** - HTTP/HTTPS interception
- **Traffic Replay** - Re-execute captured interactions
- **TLS-aware Routing** - HTTPS proxy support

---

