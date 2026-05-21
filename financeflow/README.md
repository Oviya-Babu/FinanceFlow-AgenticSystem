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
```bash
# Windows
redis-server.exe

# Linux/Mac (if installed via brew)
redis-server

# Docker
docker run -d -p 6379:6379 redis:latest
```

---

## Running the Platform

### Start FinanceFlow Server

```bash
# Development mode with hot reload
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at `http://localhost:8000`

### Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# API info
curl http://localhost:8000/

# Prometheus metrics (if enabled)
curl http://localhost:9090
```

---

## API Usage

### Start a Workflow

```bash
curl -X POST http://localhost:8000/api/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "market_analysis",
    "description": "Generate Q3 NVIDIA market analysis report",
    "parameters": {
      "company": "NVIDIA",
      "period": "Q3",
      "competitors": ["AMD", "Intel"]
    }
  }'
```

Response:
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Workflow market_analysis queued for execution"
}
```

### Get Workflow Status

```bash
curl http://localhost:8000/api/workflows/550e8400-e29b-41d4-a716-446655440000/status
```

### List All Workflows

```bash
curl http://localhost:8000/api/workflows
```

---

## Observability

### Structured Logging

All operations emit structured JSON logs:

```json
{
  "timestamp": "2024-05-21T10:30:45.123456Z",
  "level": "INFO",
  "logger": "financeflow.agents",
  "message": "Task completed successfully",
  "correlation_id": "abc-123",
  "trace_id": "xyz-789",
  "function": "execute_task",
  "agent_id": "orchestrator-agent",
  "duration_ms": 2456
}
```

### Distributed Tracing

Traces are exported to Jaeger if enabled:

```
OTEL_JAEGER_ENABLED=true
JAEGER_AGENT_HOST=localhost
JAEGER_AGENT_PORT=6831
```

Access Jaeger UI at `http://localhost:16686`

### Metrics

Prometheus metrics are exported if enabled:

```
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=9090
```

Access metrics at `http://localhost:9090`

---

## Project Structure

```
financeflow/
├── app/
│   ├── agents/          # Agent implementations
│   │   ├── base.py      # BaseAgent class
│   │   ├── orchestrator.py
│   │   ├── research.py
│   │   ├── analyst.py
│   │   └── report.py
│   ├── tools/           # Tool definitions
│   ├── memory/          # Redis memory layer
│   ├── workflows/       # Workflow definitions
│   ├── observability/   # OpenTelemetry setup
│   ├── api/            # FastAPI routes
│   ├── services/       # Database services
│   ├── models/         # Pydantic models
│   ├── config/         # Configuration
│   ├── utils/          # Utilities
│   └── main.py         # FastAPI application
├── tests/              # Test suites
├── docker/             # Docker files
├── prometheus/         # Prometheus config
├── grafana/            # Grafana dashboards
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

---

## Enterprise Workflows

### Q3 Market Analysis

```bash
curl -X POST http://localhost:8000/api/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "quarterly_market_analysis",
    "description": "Analyze Q3 market trends for NVDA, MSFT, and JPM with competitor analysis"
  }'
```

**Flow:**
1. OrchestratorAgent receives request
2. Delegates web research to ResearchAgent
3. AnalystAgent analyzes internal metrics
4. ReportAgent synthesizes executive summary
5. Results delivered to stakeholder

### Quarterly Reporting

```bash
curl -X POST http://localhost:8000/api/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "quarterly_reporting",
    "description": "Generate Q3 financial report with risk analysis and strategic recommendations"
  }'
```

### Competitor Intelligence

```bash
curl -X POST http://localhost:8000/api/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "competitor_analysis",
    "description": "Deep dive analysis of competitor market positioning and strategy"
  }'
```

---

## Testing

### Run Tests

```bash
pytest tests/ -v
```

### Run with Coverage

```bash
pytest tests/ --cov=app --cov-report=html
```

---

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

## Configuration

### Environment Variables

See `.env.example` for all available options.

**Key Variables:**

```bash
# Ollama
OLLAMA_MODEL=llama3.2:3b
OLLAMA_HOST=http://localhost:11434

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# SQLite
SQLITE_DB_PATH=./data/financeflow.db

# OpenTelemetry
OTEL_ENABLED=true
JAEGER_AGENT_HOST=localhost

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## Production Deployment

### Docker Deployment

```bash
docker-compose -f docker/docker-compose.yml up
```

### Kubernetes

See `docker/kubernetes/` for k8s manifests.

### Environment Configuration

For production:
1. Use external Redis/PostgreSQL
2. Enable TLS for all communications
3. Implement proper secret management
4. Set `FASTAPI_ENV=production`
5. Configure centralized logging (ELK, Datadog, etc)

---

## Troubleshooting

### Redis Connection Error

```
Error: Failed to connect to Redis
```

**Solution:** Ensure Redis is running on localhost:6379
```bash
redis-cli ping  # Should return PONG
```

### Ollama Connection Error

```
Error: Failed to connect to Ollama
```

**Solution:** Start Ollama and ensure model is pulled
```bash
ollama serve
ollama list  # Should show llama3.2:3b
```

### Database Lock Error

```
Error: database is locked
```

**Solution:** Delete stale database file and reinitialize
```bash
rm data/financeflow.db
```

### Import Errors

```
ModuleNotFoundError: No module named 'app'
```

**Solution:** Ensure you're running from project root with activated venv
```bash
cd financeflow
source venv/bin/activate  # Linux/Mac
```

---

## Performance Tuning

### Agent Optimization

```python
# Increase model max tokens
OLLAMA_MAX_TOKENS=4096

# Reduce temperature for more consistent output
OLLAMA_TEMPERATURE=0.3

# Increase max iterations for complex tasks
APP_AGENT_MAX_ITERATIONS=30
```

### Redis Optimization

```python
# Increase connection pool size
REDIS_CONNECTION_POOL_SIZE=20

# Use pipelining for batch operations
```

### Database Optimization

```python
# Enable WAL mode for better concurrency
SQLITE_PRAGMAS=journal_mode=WAL
```

---

## License

Proprietary - FinanceFlow Inc.

---

## Support

For issues or questions:
1. Check logs in `data/logs/`
2. Review `.env` configuration
3. Verify all services are running (Redis, Ollama)
4. Check network connectivity

---

## Roadmap

**Phase 1** ✅ Foundation (FastAPI, async runtime, LangChain, Redis, SQLite, observability)  
**Phase 2** ✅ Agent Implementation (all 4 agents)  
**Phase 3** ⏳ Tool Ecosystem (expanded tools)  
**Phase 4** ⏳ Enterprise Workflows (complex workflows)  
**Phase 5** ⏳ Attack Surface Preparation (intentional vulnerabilities)  
**Phase 6** ⏳ Observability + Telemetry (enhanced tracing)  
**Phase 7** ⏳ AgentGuard-X Integration Readiness (integration points)  

---

**Last Updated:** May 21, 2024  
**Version:** 1.0.0-Alpha
