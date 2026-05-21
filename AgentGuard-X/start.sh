#!/bin/bash
set -e

echo "=========================================="
echo "  AgentGuard-X PoC v1.1 — Startup Script"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Start Redis
echo "[1/7] Starting Redis..."
sudo systemctl start redis-server 2>/dev/null || redis-server --daemonize yes 2>/dev/null || echo "Redis may already be running"
sleep 1
redis-cli ping && echo "Redis: OK" || echo "Redis: WARNING — not responding"

# 2. Start OPA with policy
echo "[2/7] Starting OPA..."
pkill -f "opa run" 2>/dev/null || true
sleep 0.5
opa run --server --addr :8181 policies/ > /tmp/opa.log 2>&1 &
OPA_PID=$!
echo "OPA PID: $OPA_PID"
sleep 2
curl -s http://localhost:8181/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('OPA: OK' if d.get('healthy') else 'OPA: WARNING')" 2>/dev/null || echo "OPA: checking..."

# 3. Start Ollama (if not already running)
echo "[3/7] Starting Ollama..."
if ! pgrep -x ollama > /dev/null 2>&1; then
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo "Ollama PID: $OLLAMA_PID"
    sleep 3
else
    echo "Ollama already running"
fi

# Pull model if not present
echo "Checking Ollama model..."
ollama pull llama3.2 2>/dev/null || echo "Note: 'ollama pull llama3.2' if model not present"

# 4. Activate virtual environment
echo "[4/7] Activating virtual environment..."
if [ -d "agentguard-env" ]; then
    source agentguard-env/bin/activate
elif [ -d "../agentguard-env" ]; then
    source ../agentguard-env/bin/activate
else
    echo "No virtual environment found at 'agentguard-env'. Using system Python."
fi

# 5. Start Triage Engine
echo "[5/7] Starting AgentGuard-X Triage Engine..."
pkill -f "uvicorn triage.main:app" 2>/dev/null || true
sleep 0.5
uvicorn triage.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/agentguard.log 2>&1 &
TRIAGE_PID=$!
echo "Triage Engine PID: $TRIAGE_PID"
echo "Waiting for startup (model loading takes ~15-20s)..."
sleep 20

# 6. Health check
echo "[6/7] Running health check..."
python3 -c "
import requests, json, sys
try:
    r = requests.get('http://localhost:8000/health', timeout=10)
    health = r.json()
    print('Health:', json.dumps(health, indent=2))
    components = health.get('components', {})
    down = [k for k, v in components.items() if not v]
    if down:
        print(f'WARNING: Components not ready: {down}')
    else:
        print('All components: OK')
except Exception as e:
    print(f'ERROR: Health check failed: {e}')
    sys.exit(1)
"

# 7. Seed baseline data
echo "[7/7] Seeding baseline data..."
python3 demo/seed_baseline.py

echo ""
echo "=========================================="
echo "  AgentGuard-X ready."
echo "  Run demo: python3 demo/run_flows.py"
echo "  API docs: http://localhost:8000/docs"
echo "  Health:   http://localhost:8000/health"
echo "  Stats:    http://localhost:8000/stats"
echo "  Logs:     tail -f /tmp/agentguard.log"
echo "=========================================="
