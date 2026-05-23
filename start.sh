#!/usr/bin/env bash
# =============================================================================
#  start.sh  —  Start all FinanceFlow + AgentGuard-X services
#  Run from the repo root: bash start.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_ROOT/venv"
LOG_DIR="/tmp/financeflow-logs"
mkdir -p "$LOG_DIR"

if [ ! -d "$VENV" ]; then
    echo "ERROR: venv not found. Run 'bash setup-kali.sh' first."
    exit 1
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

echo "======================================================"
echo "  Starting FinanceFlow + AgentGuard-X"
echo "======================================================"

# ── Redis ─────────────────────────────────────────────────────────────────────
if redis-cli ping > /dev/null 2>&1; then
    echo "[✓] Redis already running"
else
    echo "[+] Starting Redis..."
    docker rm -f agentguard-redis >/dev/null 2>&1 || true
    if docker compose version >/dev/null 2>&1; then
        docker compose -f "$REPO_ROOT/docker-compose.yaml" up -d redis
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose -f "$REPO_ROOT/docker-compose.yaml" up -d redis
    else
        echo "ERROR: Docker Compose is not installed, and no Redis service is running."
        exit 1
    fi
    sleep 2
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[✓] Ollama already running"
else
    echo "[+] Starting Ollama..."
    docker rm -f financeflow-ollama >/dev/null 2>&1 || true
    docker run -d \
        --name financeflow-ollama \
        --restart unless-stopped \
        -p 11434:11434 \
        -v ollama_data:/root/.ollama \
        ollama/ollama:0.1.32
    sleep 5
fi

# ── OPA ───────────────────────────────────────────────────────────────────────
if curl -s http://localhost:8181/health > /dev/null 2>&1; then
    echo "[✓] OPA already running"
else
    echo "[+] Starting OPA on :8181..."
    docker rm -f agentguard-opa >/dev/null 2>&1 || true
    docker compose -f "$REPO_ROOT/docker-compose.yaml" up -d opa
    sleep 5
fi

# ── AgentGuard-X (:8001) ──────────────────────────────────────────────────────
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "[✓] AgentGuard-X already running"
else
    echo "[+] Starting AgentGuard-X on :8001..."
    cd "$REPO_ROOT"
    python AgentGuard-X/run.py > "$LOG_DIR/agentguardx.log" 2>&1 &
    echo $! > "$LOG_DIR/agentguardx.pid"
    sleep 3
fi

# ── FinanceFlow (:8000) ───────────────────────────────────────────────────────
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "[✓] FinanceFlow already running"
else
    echo "[+] Starting FinanceFlow on :8000..."
    cd "$REPO_ROOT/financeflow"
    python run.py > "$LOG_DIR/financeflow.log" 2>&1 &
    echo $! > "$LOG_DIR/financeflow.pid"
    cd "$REPO_ROOT"
    sleep 3
fi

# ── Health checks ─────────────────────────────────────────────────────────────
echo ""
echo "  Health checks:"
curl -s http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  FinanceFlow  → {d.get(\"status\",\"?\")} ({d.get(\"service\",\"\")} {d.get(\"version\",\"\")})')" 2>/dev/null || echo "  FinanceFlow  → not responding yet"
curl -s http://localhost:8001/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  AgentGuard-X → {d.get(\"status\",\"?\")} | redis={d.get(\"components\",{}).get(\"redis\",\"?\")} opa={d.get(\"components\",{}).get(\"opa\",\"?\")} ollama={d.get(\"components\",{}).get(\"ollama\",\"?\")}')" 2>/dev/null || echo "  AgentGuard-X → not responding yet"

echo ""
echo "  Logs in $LOG_DIR"
echo "  To stop: bash stop.sh"
echo "======================================================"
