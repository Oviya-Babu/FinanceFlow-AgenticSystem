import os

# ─── Service endpoints ────────────────────────────────────────────────────────
TRIAGE_SERVICE_URL = os.getenv("TRIAGE_SERVICE_URL", "http://localhost:8000")
TRIAGE_ENDPOINT    = "/triage"
TRIAGE_PORT        = int(os.getenv("TRIAGE_PORT", "8000"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2")

# ─── Redis ────────────────────────────────────────────────────────────────────
REDIS_HOST     = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT     = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None   # empty string → None

SESSION_WINDOW_SIZE = 50
SESSION_KEY_PREFIX  = "agentguard:session:"
BASELINE_KEY_PREFIX = "agentguard:baseline:"

# ─── OPA ─────────────────────────────────────────────────────────────────────
OPA_URL         = os.getenv("OPA_URL", "http://localhost:8181")
OPA_POLICY_PATH = os.getenv("OPA_POLICY_PATH", "/v1/data/agentguard/authz")

# ─── Scoring thresholds ───────────────────────────────────────────────────────
FAST_PATH_THRESHOLD  = float(os.getenv("FAST_PATH_THRESHOLD",  "0.30"))
INSTANT_KILL_THRESHOLD = float(os.getenv("INSTANT_KILL_THRESHOLD", "0.80"))
STAGE2_INSTANT_KILL  = float(os.getenv("STAGE2_INSTANT_KILL",  "0.95"))

# ─── Stage weights (must sum to 1.0) ─────────────────────────────────────────
WEIGHT_SIGNATURE = float(os.getenv("WEIGHT_SIGNATURE", "0.35"))
WEIGHT_POLICY    = float(os.getenv("WEIGHT_POLICY",    "0.30"))
WEIGHT_SEMANTIC  = float(os.getenv("WEIGHT_SEMANTIC",  "0.20"))
WEIGHT_DRIFT     = float(os.getenv("WEIGHT_DRIFT",     "0.15"))

# ─── Corroboration ────────────────────────────────────────────────────────────
CORROBORATION_THRESHOLD  = int(os.getenv("CORROBORATION_THRESHOLD",  "2"))
CORROBORATION_MULTIPLIER = float(os.getenv("CORROBORATION_MULTIPLIER", "1.25"))

# ─── Stage timeouts (seconds) ─────────────────────────────────────────────────
STAGE3_TIMEOUT = 0.500
STAGE4_TIMEOUT = 2.000
STAGE5_TIMEOUT = 0.100

# ─── ChromaDB / RAG ───────────────────────────────────────────────────────────
CHROMA_COLLECTION_NAME  = os.getenv("CHROMA_COLLECTION", "threat_patterns")
EMBEDDING_MODEL         = os.getenv("EMBEDDING_MODEL",   "all-MiniLM-L6-v2")
RAG_TOP_K               = int(os.getenv("RAG_TOP_K",   "5"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.65"))

# ─── Docker sandbox ───────────────────────────────────────────────────────────
SANDBOX_IMAGE           = os.getenv("SANDBOX_IMAGE",   "python:3.11-slim")
SANDBOX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_TIMEOUT", "30"))
SANDBOX_MEMORY_LIMIT    = os.getenv("SANDBOX_MEMORY",  "256m")
SANDBOX_CPU_QUOTA       = 50000

# ─── Review queue ─────────────────────────────────────────────────────────────
REVIEW_QUEUE_KEY        = "agentguard:review_queue"
REVIEW_QUEUE_SCORE_FLOOR = 0.30

# ─── Agent registry ───────────────────────────────────────────────────────────
# Maps agent_id → {role, owner}.  Must match FinanceFlow agent IDs exactly.
REGISTERED_AGENTS = {
    # Canonical demo agents
    "orchestrator-001": {"role": "orchestrator_agent", "owner": "financeflow"},
    "research-001":     {"role": "research_agent",     "owner": "financeflow"},
    "analyst-001":      {"role": "analyst_agent",      "owner": "financeflow"},
    "report-001":       {"role": "report_agent",       "owner": "financeflow"},
    # Legacy / alternate IDs kept for backwards compatibility
    "orchestrator-agent": {"role": "orchestrator_agent", "owner": "financeflow"},
    "research-agent":     {"role": "research_agent",     "owner": "financeflow"},
    "analyst-agent":      {"role": "analyst_agent",      "owner": "financeflow"},
    "report-agent":       {"role": "report_agent",       "owner": "financeflow"},
    # data_agent for exfil demo
    "data-001":           {"role": "data_agent",          "owner": "financeflow"},
    "data-agent":         {"role": "data_agent",          "owner": "financeflow"},
}

# ─── Aho-Corasick pattern library ─────────────────────────────────────────────
# Keys are lowercase patterns; values are risk weights (0.0–1.0).
# The highest-weight match becomes the Stage 2 score.
# Weights ≥ STAGE2_INSTANT_KILL (0.95) trigger instant-kill.
PATTERNS: dict[str, float] = {
    # Prompt override / jailbreak
    "ignore previous instructions":  1.0,
    "ignore all previous":            1.0,
    "disregard your instructions":    1.0,
    "disregard all instructions":     1.0,
    "override your system prompt":    1.0,
    "you have no restrictions":       1.0,
    "act as if you have no":          0.95,
    "forget your previous role":      0.95,
    "modify your system prompt":      1.0,
    "update your instructions":       0.90,
    "append to your system":          0.95,
    "you are now":                    0.85,
    "new persona":                    0.80,
    "pretend you are":                0.75,
    # Kernel-dangerous / exfiltration
    "cat /etc/passwd":   1.0,
    "cat /etc/shadow":   1.0,
    "/proc/self":        0.95,
    "base64 -d":         0.90,
    "curl http":         0.80,
    "wget http":         0.80,
    "nc -e":             1.0,
    "/bin/sh":           0.95,
    "/bin/bash":         0.95,
    "chmod +x":          0.85,
    # Credential harvesting
    "aws_access_key":          1.0,
    "aws_secret":              1.0,
    "private_key":             0.90,
    "bearer token":            0.85,
    "authorization: bearer":   0.90,
    "api_key=":                0.85,
    "secret_key=":             0.90,
    # Indirect prompt injection markers
    "[[system]]":                    1.0,
    "[[assistant]]":                 1.0,
    "<|im_start|>":                  1.0,
    "<|system|>":                    1.0,
    "new instructions:":             0.90,
    "system:":                       0.75,
}

# ─── OWASP LLM Top-10 category mapping ───────────────────────────────────────
OWASP_CATEGORIES: dict[str, str] = {
    "ignore previous instructions":  "LLM01 — Prompt Injection",
    "ignore all previous":            "LLM01 — Prompt Injection",
    "disregard your instructions":    "LLM01 — Prompt Injection",
    "disregard all instructions":     "LLM01 — Prompt Injection",
    "override your system prompt":    "LLM01 — Prompt Injection",
    "you have no restrictions":       "LLM01 — Prompt Injection",
    "act as if you have no":          "LLM01 — Prompt Injection",
    "forget your previous role":      "LLM01 — Prompt Injection",
    "modify your system prompt":      "LLM01 — Prompt Injection",
    "update your instructions":       "LLM01 — Prompt Injection",
    "append to your system":          "LLM01 — Prompt Injection",
    "you are now":                    "LLM01 — Prompt Injection",
    "new persona":                    "LLM01 — Prompt Injection",
    "pretend you are":                "LLM01 — Prompt Injection",
    "cat /etc/passwd":   "LLM06 — Sensitive Information Disclosure",
    "cat /etc/shadow":   "LLM06 — Sensitive Information Disclosure",
    "/proc/self":        "LLM06 — Sensitive Information Disclosure",
    "base64 -d":         "LLM06 — Sensitive Information Disclosure",
    "curl http":         "LLM06 — Sensitive Information Disclosure",
    "wget http":         "LLM06 — Sensitive Information Disclosure",
    "nc -e":             "LLM06 — Sensitive Information Disclosure",
    "/bin/sh":           "LLM06 — Sensitive Information Disclosure",
    "/bin/bash":         "LLM06 — Sensitive Information Disclosure",
    "chmod +x":          "LLM06 — Sensitive Information Disclosure",
    "aws_access_key":          "LLM06 — Sensitive Information Disclosure",
    "aws_secret":              "LLM06 — Sensitive Information Disclosure",
    "private_key":             "LLM06 — Sensitive Information Disclosure",
    "bearer token":            "LLM06 — Sensitive Information Disclosure",
    "authorization: bearer":   "LLM06 — Sensitive Information Disclosure",
    "api_key=":                "LLM06 — Sensitive Information Disclosure",
    "secret_key=":             "LLM06 — Sensitive Information Disclosure",
    "[[system]]":              "LLM01 — Prompt Injection",
    "[[assistant]]":           "LLM01 — Prompt Injection",
    "<|im_start|>":            "LLM01 — Prompt Injection",
    "<|system|>":              "LLM01 — Prompt Injection",
    "new instructions:":       "LLM01 — Prompt Injection",
    "system:":                 "LLM01 — Prompt Injection",
}
