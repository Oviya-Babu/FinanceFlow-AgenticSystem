#!/usr/bin/env bash
# =============================================================================
#  setup-kali.sh  —  One-time environment setup for Kali Linux (Python 3.13)
#  Run from the repo root: bash setup-kali.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_ROOT/venv"

echo "======================================================"
echo "  FinanceFlow + AgentGuard-X  —  Kali Linux Setup"
echo "======================================================"

# ── 1. System packages ────────────────────────────────────────────────────────
echo ""
echo "[1/8] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    redis-server \
    docker.io \
    git \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    curl \
    wget \
    libssl-dev \
    libffi-dev

# ── 2. Redis ──────────────────────────────────────────────────────────────────
echo ""
echo "[2/8] Starting Redis..."
sudo systemctl enable redis-server --quiet
sudo systemctl start redis-server
redis-cli ping | grep -q PONG && echo "    Redis OK" || echo "    WARNING: Redis ping failed"

# ── 3. Ollama ─────────────────────────────────────────────────────────────────
echo ""
echo "[3/8] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.ai/install.sh | sh
else
    echo "    Ollama already installed: $(ollama --version 2>/dev/null || true)"
fi

echo "    Starting Ollama daemon..."
ollama serve > /tmp/ollama-setup.log 2>&1 &
OLLAMA_PID=$!
sleep 4  # give the daemon time to start

echo "    Pulling model llama3.2:3b (this may take a few minutes)..."
ollama pull llama3.2:3b || echo "    WARNING: model pull failed — run 'ollama pull llama3.2:3b' manually"

kill $OLLAMA_PID 2>/dev/null || true

# ── 4. OPA (Open Policy Agent) ────────────────────────────────────────────────
echo ""
echo "[4/8] Installing OPA..."
if ! command -v opa &>/dev/null; then
    OPA_VERSION="$(curl -s https://api.github.com/repos/open-policy-agent/opa/releases/latest | grep '"tag_name"' | cut -d'"' -f4)"
    OPA_VERSION="${OPA_VERSION:-v0.68.0}"
    curl -sL "https://github.com/open-policy-agent/opa/releases/download/${OPA_VERSION}/opa_linux_amd64_static" \
         -o /tmp/opa
    chmod +x /tmp/opa
    sudo mv /tmp/opa /usr/local/bin/opa
    echo "    OPA installed: $(opa version | head -1)"
else
    echo "    OPA already installed: $(opa version | head -1)"
fi

# ── 5. Docker group ───────────────────────────────────────────────────────────
echo ""
echo "[5/8] Configuring Docker..."
sudo systemctl enable docker --quiet
sudo systemctl start docker
sudo usermod -aG docker "$USER" 2>/dev/null || true
echo "    Docker OK (you may need to log out/in for group membership to take effect)"

# ── 6. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "[6/8] Creating Python virtual environment at $VENV ..."
python3 -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install --upgrade pip wheel setuptools -q

# Install PyTorch CPU-only FIRST (sentence-transformers depends on it)
echo "    Installing PyTorch CPU build..."
pip install torch --index-url https://download.pytorch.org/whl/cpu -q

echo "    Installing FinanceFlow dependencies..."
pip install -r "$REPO_ROOT/financeflow/requirements.txt" -q

echo "    Installing AgentGuard-X dependencies..."
pip install -r "$REPO_ROOT/AgentGuard-X/requirements.txt" -q

# ── 7. spaCy language model (required by presidio-analyzer) ───────────────────
echo ""
echo "[7/8] Downloading spaCy language model..."
python -m spacy download en_core_web_lg -q || \
python -m spacy download en_core_web_sm -q || \
echo "    WARNING: spaCy model download failed — run 'python -m spacy download en_core_web_lg' manually"

deactivate

# ── 8. .env file ──────────────────────────────────────────────────────────────
echo ""
echo "[8/8] Setting up .env..."
if [ ! -f "$REPO_ROOT/financeflow/.env" ]; then
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/financeflow/.env"
    echo "    Created financeflow/.env from .env.example"
else
    echo "    financeflow/.env already exists — skipping"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit financeflow/.env if needed"
echo "    2. bash start.sh        # start everything"
echo "    3. bash stop.sh         # stop everything"
echo ""
echo "  Ports:"
echo "    FinanceFlow  → http://localhost:8000"
echo "    AgentGuard-X → http://localhost:8001"
echo "    OPA          → http://localhost:8181"
echo "    Redis        → localhost:6379"
echo "    Ollama       → http://localhost:11434"
echo "======================================================"
