#!/usr/bin/env bash
# =============================================================================
#  stop.sh  —  Stop all FinanceFlow + AgentGuard-X services
# =============================================================================
LOG_DIR="/tmp/financeflow-logs"

_stop() {
    local name="$1"
    local pidfile="$LOG_DIR/$2.pid"
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && echo "  [✓] $name stopped (pid $pid)"
        else
            echo "  [–] $name was not running"
        fi
        rm -f "$pidfile"
    else
        echo "  [–] $name — no pid file"
    fi
}

echo "Stopping services..."
_stop "FinanceFlow"  "financeflow"
_stop "AgentGuard-X" "agentguardx"
_stop "OPA"          "opa"
_stop "Ollama"       "ollama"
echo "Done."
