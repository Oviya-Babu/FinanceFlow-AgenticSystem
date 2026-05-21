TRIAGE_SERVICE_URL = "http://localhost:8001"
TRIAGE_ENDPOINT = "/triage"

# Scoring thresholds
FAST_PATH_THRESHOLD = 0.30
INSTANT_KILL_THRESHOLD = 0.80

# Stage weights (must sum to 1.0)
WEIGHT_SIGNATURE = 0.35
WEIGHT_POLICY = 0.30
WEIGHT_SEMANTIC = 0.20
WEIGHT_DRIFT = 0.15

# Corroboration multiplier
CORROBORATION_THRESHOLD = 2
CORROBORATION_MULTIPLIER = 1.25

# Stage 2 instant-kill threshold (within-stage, before aggregation)
STAGE2_INSTANT_KILL = 0.95

# Redis
REDIS_HOST = "localhost"
REDIS_PORT = 6379
SESSION_WINDOW_SIZE = 50

# OPA
OPA_URL = "http://localhost:8181"
OPA_POLICY_PATH = "/v1/data/agentguard/authz"

# ChromaDB
CHROMA_COLLECTION_NAME = "threat_patterns"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
RAG_TOP_K = 5
RAG_SIMILARITY_THRESHOLD = 0.65

# Docker sandbox
SANDBOX_IMAGE = "python:3.11-slim"
SANDBOX_TIMEOUT_SECONDS = 30
SANDBOX_MEMORY_LIMIT = "256m"
SANDBOX_CPU_QUOTA = 50000

# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"

# Review queue
REVIEW_QUEUE_KEY = "agentguard:review_queue"
REVIEW_QUEUE_SCORE_FLOOR = 0.30

# Agent registry — must match FinanceFlow agent IDs and roles exactly
REGISTERED_AGENTS = {
    "orchestrator-agent": {"role": "orchestrator",    "owner": "financeflow"},
    "research-agent":     {"role": "research_agent",  "owner": "financeflow"},
    "analyst-agent":      {"role": "analyst_agent",   "owner": "financeflow"},
    "report-agent":       {"role": "report_agent",    "owner": "financeflow"},
}

# Redis key prefixes
BASELINE_KEY_PREFIX = "agentguard:baseline:"
SESSION_KEY_PREFIX  = "agentguard:session:"

# Stage timeouts (seconds)
STAGE3_TIMEOUT = 0.500
STAGE4_TIMEOUT = 2.000
STAGE5_TIMEOUT = 0.100
