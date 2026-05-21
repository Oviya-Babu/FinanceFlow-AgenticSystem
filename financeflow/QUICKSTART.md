# Quick Start Guide - FinanceFlow Platform

## 5-Minute Setup

### 1. Prerequisites

- Python 3.11+
- Redis (Windows: `choco install redis-64` or Docker)
- Ollama (https://ollama.ai/)

### 2. Windows Setup

```bash
# Run setup script
setup.bat

# Activate virtual environment
venv\Scripts\activate

# Start Redis (new terminal)
redis-server.exe

# Start Ollama (new terminal)
ollama serve

# Pull model (new terminal)
ollama pull llama3.2:3b

# Run FinanceFlow (first terminal)
python -m uvicorn app.main:app --reload
```

### 3. Linux/Mac Setup

```bash
# Run setup script
chmod +x setup.sh
./setup.sh

# Activate virtual environment
source venv/bin/activate

# Start Redis (new terminal)
redis-server

# Start Ollama (new terminal)
ollama serve

# Pull model (new terminal)
ollama pull llama3.2:3b

# Run FinanceFlow (first terminal)
python -m uvicorn app.main:app --reload
```

### 4. Docker Setup (All-in-One)

```bash
cd docker
docker-compose up

# In new terminal, pull Ollama model
docker exec financeflow-ollama ollama pull llama3.2:3b
```

## Testing the Platform

### Health Check
```bash
curl http://localhost:8000/health
```

### Start a Workflow
```bash
curl -X POST http://localhost:8000/api/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "test_analysis",
    "description": "Test market analysis for NVDA",
    "parameters": {"company": "NVDA"}
  }'
```

### Monitor Workflow
```bash
# Copy workflow_id from previous response
curl http://localhost:8000/api/workflows/{workflow_id}/status
```

## Observability Access

- **API**: http://localhost:8000
- **Prometheus Metrics**: http://localhost:9090 (if enabled)
- **Jaeger Traces**: http://localhost:16686 (if enabled)
- **Grafana Dashboard**: http://localhost:3000 (if enabled)

## Common Issues

### "Redis connection refused"
- Ensure Redis is running: `redis-cli ping`
- Should respond with `PONG`

### "Ollama connection refused"
- Ensure Ollama is running: `ollama list`
- Should list available models

### "Module not found" errors
- Activate virtual environment: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

## Next Steps

1. Review [README.md](README.md) for complete documentation
2. Check [app/agents/](app/agents/) for agent implementations
3. Explore [app/api/routes/](app/api/routes/) for API endpoints
4. Run tests: `pytest tests/ -v`

## Architecture Overview

```
User Request
    ↓
FastAPI Server (async)
    ↓
OrchestratorAgent (LangChain)
    ↓
    ├→ ResearchAgent (web search, docs)
    ├→ AnalystAgent (analysis, modeling)
    └→ ReportAgent (report generation)
    ↓
OpenTelemetry Tracing
    ├→ Jaeger (distributed traces)
    ├→ Prometheus (metrics)
    └→ Structured JSON Logs
    ↓
Response
```

## Key Features

✅ Real async agents (not mocked)
✅ Dynamic tool execution
✅ Inter-agent communication
✅ Observability by design
✅ Enterprise-grade architecture
✅ Integration-ready for AgentGuard-X

## Important Notes

- FinanceFlow is intentionally vulnerable (no security enforcement)
- AgentGuard-X will be responsible for security later
- All agent reasoning is dynamic (not hardcoded)
- Workflows generate realistic telemetry
- Designed for security testing and research

---

For detailed documentation, see [README.md](README.md)
