# OPA Policy Rules Documentation

## Overview

This document describes the production-grade Open Policy Agent (OPA) policies for AgentGuard-X gateway with FinanceFlow agentic system.

**File Structure:**
- `policies/tool_rbac.rego` - Intent-binding rules (tool allowlists, velocity limits)
- `policies/state_based_privilege.rego` - Context-aware rules (tool + context → allow/deny)
- `policies/resource_velocity.rego` - Velocity limits (per_sec, per_min, per_hour)

**Security Model:**
- **Default: DENY** - All access denied unless explicitly allowed
- **Fail-Closed** - OPA unreachable → DENY (no fallback)
- **Deterministic** - Same input always produces same output
- **Traceable** - Every decision includes reasoning

---

## Part 1: Intent-Binding Rules (`tool_rbac.rego`)

Intent-binding determines: "Can this agent use this tool?"

### 1.1 FinanceFlow Agent Definitions

**OrchestratorAgent** (Orchestrator)
- **Role**: Spawns and manages other agents (Research, Analyst, Report)
- **Level**: Orchestration (top-level)
- **Allowed Tools**: `spawn_agent` (only)
- **Denied Tools**: web_search, query_internal_db, read_pdf, write_report, send_email
- **Parent**: None (top-level)

```rego
allowed_tools: ["spawn_agent"]
denied_tools: [web_search, read_pdf, query_internal_db, write_report, send_email, ...]
```

**ResearchAgent** (Research)
- **Role**: Web search and document analysis
- **Level**: Worker
- **Allowed Tools**: `web_search`, `read_pdf`, `fetch_url`
- **Denied Tools**: query_internal_db, write_report, send_email, spawn_agent
- **Parent**: orchestrator_agent

```rego
allowed_tools: ["web_search", "read_pdf", "fetch_url"]
denied_tools: [query_internal_db, write_report, send_email, spawn_agent, ...]
```

**AnalystAgent** (Analyst)
- **Role**: Internal database queries and analytics
- **Level**: Worker
- **Allowed Tools**: `query_internal_db`, `write_report`, `fetch_dataset`
- **Denied Tools**: web_search, read_pdf, send_email, spawn_agent
- **Parent**: orchestrator_agent

```rego
allowed_tools: ["query_internal_db", "write_report", "fetch_dataset"]
denied_tools: [web_search, read_pdf, send_email, spawn_agent, ...]
```

**ReportAgent** (Report)
- **Role**: Final reporting and notifications
- **Level**: Worker
- **Allowed Tools**: `write_report`, `send_email`
- **Denied Tools**: web_search, query_internal_db, read_pdf, spawn_agent
- **Parent**: orchestrator_agent

```rego
allowed_tools: ["write_report", "send_email"]
denied_tools: [web_search, query_internal_db, read_pdf, spawn_agent, ...]
```

### 1.2 Intent-Binding Decision Logic

```
Rule: allow_basic if {
    // Step 1: Check explicit denylist (supercedes allowlist)
    tool NOT in role_tool_denylist[role]
    
    // Step 2: Check allowlist (exact match or pattern match)
    tool IN role_tool_allowlist[role] OR tool matches pattern
}

Default: DENY
```

**Example:**
- Input: `{agent_role: "research_agent", tool_name: "web_search"}`
  1. Check denylist: "web_search" NOT in denylist[research_agent] ✓
  2. Check allowlist: "web_search" IN allowlist[research_agent] ✓
  3. Result: **ALLOW**

- Input: `{agent_role: "research_agent", tool_name: "query_internal_db"}`
  1. Check denylist: "query_internal_db" IN denylist[research_agent] ✗
  2. Result: **DENY** (fails at step 1)

### 1.3 Regex Pattern Matching

Some tools support wildcards for tool families:

| Pattern | Description | Allowed Agents |
|---------|-------------|-----------------|
| `read_file.*` | Read any file type | research_agent, analyst_agent |
| `write_file.*` | Write any file type | (none - too risky) |

**Example:** Tool `read_file_config` matches pattern `read_file.*`

### 1.4 Basic Velocity Limits (Per-Role)

Coarse-grained limits. Fine-grained per-tool limits in `resource_velocity.rego`.

| Agent | per_sec | per_min | per_hour | Description |
|-------|---------|---------|----------|-------------|
| orchestrator_agent | 1 | 10 | 100 | Orchestration overhead minimal |
| research_agent | 5 | 100 | 1,000 | Web search and PDF analysis |
| analyst_agent | 10 | 200 | 5,000 | Database queries and reporting |
| report_agent | 3 | 50 | 500 | Reporting and notifications |

**Usage:** Preliminary check before state-based and velocity rules.

---

## Part 2: State-Based Privilege Rules (`state_based_privilege.rego`)

State-based rules determine: "Can this agent use this tool **with this context**?"

### 2.1 Context-Aware Restrictions

After intent-binding allows access, context is evaluated for specific tools.

**Tools Requiring Context:**
- `read_pdf`
- `query_internal_db`
- `write_report`
- `send_email`

**Tools NOT Requiring Context:**
- `spawn_agent`
- `web_search`
- `fetch_url`
- `fetch_dataset`

### 2.2 ResearchAgent Context Rules

**Tool: `read_pdf`**

| Context | Status | Reason |
|---------|--------|--------|
| `public_documents` | ✅ ALLOW | Public content is safe |
| `internal_files` | ❌ DENY | Confidential internal docs |
| `confidential_docs` | ❌ DENY | Company secrets |

```rego
allow_context if {
    input.agent_role == "research_agent"
    input.tool_name == "read_pdf"
    input.tool_context == "public_documents"
}
```

### 2.3 AnalystAgent Context Rules

**Tool: `query_internal_db`**

| Context | Status | Reason |
|---------|--------|--------|
| `public_db` | ✅ ALLOW | Non-sensitive data |
| `analytics_db` | ✅ ALLOW | Analysis permitted for analysts |
| `admin_db` | ❌ DENY | Admin-only database |
| `audit_trail` | ❌ DENY | Audit logs off-limits |
| `financial_accounts` | ❌ DENY | Financial data restricted |

```rego
allow_context if {
    input.agent_role == "analyst_agent"
    input.tool_name == "query_internal_db"
    input.tool_context in ["public_db", "analytics_db"]
}
```

**Tool: `write_report`**

| Context | Status | Reason |
|---------|--------|--------|
| `analytics_reports` | ✅ ALLOW | Analytics reports permitted |
| `temp_reports` | ✅ ALLOW | Temporary drafts OK |
| `system_config` | ❌ DENY | System configuration off-limits |
| `audit_trail` | ❌ DENY | Audit logs cannot be modified |
| `financial_statements` | ❌ DENY | Financial reports restricted |

### 2.4 ReportAgent Context Rules

**Tool: `send_email`**

| Context | Status | Reason |
|---------|--------|--------|
| `internal_team` | ✅ ALLOW | Team distribution OK |
| `internal_distribution` | ✅ ALLOW | Company distribution lists |
| `external_distribution` | ❌ DENY | External recipients restricted |
| `vendor_emails` | ❌ DENY | Vendor communication off-limits |
| `public_lists` | ❌ DENY | Public distribution prohibited |

```rego
allow_context if {
    input.agent_role == "report_agent"
    input.tool_name == "send_email"
    input.tool_context in ["internal_team", "internal_distribution"]
}
```

**Tool: `write_report`**

| Context | Status | Reason |
|---------|--------|--------|
| `final_reports` | ✅ ALLOW | Final report generation |
| `email_reports` | ✅ ALLOW | Reports for email distribution |
| `system_config` | ❌ DENY | System configuration protected |
| `audit_trail` | ❌ DENY | Audit logs protected |
| `draft_templates` | ❌ DENY | Template modification restricted |

### 2.5 OrchestratorAgent Context Rules

**Tool: `spawn_agent`**

| Context | Status | Reason |
|---------|--------|--------|
| `standard_workflow` | ✅ ALLOW | Normal workflow OK |
| `emergency_override` | ❌ DENY | Emergency mode requires special approval |

### 2.6 Context Decision Logic

```
Rule: allow_composite if {
    // Case 1: Tool doesn't require context
    NOT (tool IN tools_requiring_context) AND
    allow_basic == true
    
    // Case 2: Tool requires context
    OR (tool IN tools_requiring_context) AND
       context_provided AND
       allow_basic == true AND
       allow_context == true
}

Default: DENY
```

---

## Part 3: Resource & Velocity Rules (`resource_velocity.rego`)

Velocity rules determine: "Can this agent make this request **right now** without hitting rate limits?"

### 3.1 Velocity Configuration

Three-tier limits: per_sec (hard stop), per_min (soft warning), per_hour (monitoring).

**Soft vs Hard Limits:**
- **Soft Limit**: Request allowed but monitored, may be routed to SANDBOX mode
- **Hard Limit**: Request blocked immediately (DENY)

### 3.2 Per-Agent, Per-Tool Limits

#### OrchestratorAgent

| Tool | per_sec | per_min | per_hour | Notes |
|------|---------|---------|----------|-------|
| spawn_agent | 1 (hard: 1) | 10 (hard: 10) | 100 (hard: 100) | Orchestration overhead minimal |

#### ResearchAgent

| Tool | per_sec | per_min | per_hour | Notes |
|------|---------|---------|----------|-------|
| web_search | 5 (hard: 10) | 100 (hard: 200) | 1,000 (hard: 2,000) | Search throttling light |
| read_pdf | 2 (hard: 5) | 40 (hard: 100) | 600 (hard: 1,000) | PDF parsing CPU-intensive |
| fetch_url | 5 (hard: 10) | 100 (hard: 200) | 1,000 (hard: 2,000) | URL fetching standard |

#### AnalystAgent

| Tool | per_sec | per_min | per_hour | Notes |
|------|---------|---------|----------|-------|
| query_internal_db | 5 (hard: 10) | 120 (hard: 200) | 4,000 (hard: 5,000) | DB queries critical path |
| write_report | 2 (hard: 10) | 50 (hard: 200) | 4,000 (hard: 5,000) | Report generation variable |
| fetch_dataset | 3 (hard: 10) | 80 (hard: 200) | 3,000 (hard: 5,000) | Dataset retrieval standard |

#### ReportAgent

| Tool | per_sec | per_min | per_hour | Notes |
|------|---------|---------|----------|-------|
| write_report | 1.5 (hard: 3) | 30 (hard: 50) | 400 (hard: 500) | Final reports carefully throttled |
| send_email | 1 (hard: 3) | 20 (hard: 50) | 400 (hard: 500) | Email rate limiting stringent |

### 3.3 Velocity Decision Logic

```
Rule: allow_velocity if {
    current_call_count_per_sec < hard_limit_per_sec AND
    current_call_count_per_min < hard_limit_per_min AND
    current_call_count_per_hour < hard_limit_per_hour
}

Rule: route_to_sandbox if {
    current_call_count >= soft_limit AND
    current_call_count < hard_limit
}

Decision:
    hard_limit_exceeded → BLOCK (DENY)
    soft_limit_exceeded → SANDBOX (ALLOW but monitor/throttle)
    within_limits → ALLOW (normal execution)

Default: DENY
```

### 3.4 Velocity Status Output

OPA returns velocity_status for each decision:

| Status | Meaning | Action |
|--------|---------|--------|
| `ok` | Within all limits | Execute normally |
| `soft_limit_approaching` | At soft limit | Route to SANDBOX (monitor) |
| `hard_limit_exceeded` | At hard limit | DENY request |
| `unknown` | Cannot determine | DENY (fail-closed) |

---

## Part 4: Decision Traceability

Every OPA decision includes a `decision_trace` array showing rule evaluation order.

### 4.1 Example Trace (Allow Case)

Request:
```json
{
  "agent_role": "research_agent",
  "tool_name": "web_search"
}
```

Response:
```json
{
  "allow": true,
  "decision_trace": [
    {
      "stage": "intent_binding",
      "agent_role": "research_agent",
      "tool_name": "web_search",
      "result": "allow",
      "reason": "Tool in allowlist for agent role"
    },
    {
      "stage": "state_privilege",
      "result": "allow",
      "reason": "Tool does not require context"
    }
  ]
}
```

### 4.2 Example Trace (Deny Case)

Request:
```json
{
  "agent_role": "analyst_agent",
  "tool_name": "web_search"
}
```

Response:
```json
{
  "allow": false,
  "decision_trace": [
    {
      "stage": "intent_binding",
      "agent_role": "analyst_agent",
      "tool_name": "web_search",
      "result": "deny",
      "reason": "Tool not in allowlist or in denylist"
    }
  ]
}
```

### 4.3 Example Trace (Context Deny)

Request:
```json
{
  "agent_role": "research_agent",
  "tool_name": "read_pdf",
  "tool_context": "internal_files"
}
```

Response:
```json
{
  "allow": false,
  "decision_trace": [
    {
      "stage": "intent_binding",
      "result": "allow",
      "reason": "Tool in allowlist for agent role"
    },
    {
      "stage": "state_privilege",
      "result": "deny",
      "reason": "Context internal_files not allowed for read_pdf"
    }
  ]
}
```

---

## Part 5: Fail-Closed Behavior

### 5.1 OPA Unavailable

If OPA is unreachable (connection error, timeout > 100ms):
- **Decision**: DENY
- **Reason**: "Policy engine unavailable"
- **Logging**: WARNING log with request details

```
[WARNING] RBAC check failed
  agent_id: "research_agent"
  tool_name: "web_search"
  error: "HTTPConnectError"
  request_id: "req-12345"
```

### 5.2 Unknown Agent Role

If agent_role is not in metadata:
- **Decision**: DENY
- **Reason**: "Agent role not recognized"
- **Logging**: WARNING log

### 5.3 Unknown Tool

If tool_name is not in any agent's allowlist:
- **Decision**: DENY
- **Reason**: "Tool not in allowlist"
- **Logging**: INFO log (expected case)

### 5.4 Malformed Input

If input is missing required fields:
- **Decision**: DENY
- **Reason**: "Invalid policy input"
- **Logging**: WARNING log with details

---

## Part 6: Determinism Guarantees

All policies are **deterministic** - same input always produces same output.

### 6.1 No Randomness

- No random number generation
- No time-dependent decisions (except velocity windows which are caller-provided)
- No external API calls within policy evaluation
- No order-dependent logic

### 6.2 Verification

Run same request 10 times:
```bash
for i in {1..10}; do
  curl -s http://localhost:8182/v1/data/agentguard/allow \
    -d '{"input": {"agent_role":"research_agent","tool_name":"web_search"}}'
done
```

All 10 responses must be identical:
```json
{
  "result": {
    "allow": true,
    "decision_trace": [...]
  }
}
```

---

## Part 7: Performance Characteristics

### 7.1 Decision Latency

- **Target**: < 3ms per decision
- **Hard Timeout**: 100ms (enforced by gateway)
- **Measured (Docker)**: ~1-2ms typical

### 7.2 Policy Compilation

- **Startup**: ~50ms to load and compile all policies
- **Runtime**: No recompilation needed (stateless evaluation)

### 7.3 Scalability

- **Concurrent Requests**: OPA handles 1000+ concurrent requests
- **Throughput**: ~300+ decisions/second per OPA instance

---

## Part 8: Debugging & Troubleshooting

### 8.1 Decision Validation Endpoint

```bash
POST /api/opa/validate
Response: {
  "valid": true,
  "errors": [],
  "warnings": [],
  "policies": ["tool_rbac", "state_based_privilege", "resource_velocity"]
}
```

### 8.2 Policy Testing Endpoint

```bash
POST /api/opa/test
Response: {
  "passed": 20,
  "failed": 0,
  "total": 20,
  "coverage": "100%",
  "tests": [...]
}
```

### 8.3 Decision Debug Endpoint

```bash
GET /api/opa/debug/{agent_id}/{tool_name}?context=public_documents
Response: {
  "agent_id": "research_agent",
  "tool_name": "read_pdf",
  "tool_context": "public_documents",
  "decision": "allow",
  "trace": [...]
}
```

### 8.4 Debugging a Denied Decision

To understand why a request was denied:

1. Check decision_trace in OPA response
2. Call debug endpoint with same parameters
3. Review state-based privilege rules for tool+context
4. Verify agent is in metadata
5. Check velocity metrics

Example:
```bash
# Denied: Why?
curl "http://localhost:8182/v1/data/agentguard/allow" \
  -d '{"input":{"agent_role":"analyst_agent","tool_name":"web_search"}}'

# Response shows reason in trace:
# "Tool not in allowlist or in denylist"

# Debug with trace:
curl "http://localhost:8000/api/opa/debug/analyst_agent/web_search"

# Conclusion: analyst_agent simply doesn't have web_search in allowlist
# This is by design - analysts should not search the web
```

---

## Part 9: Security Best Practices

### 9.1 Adding New Agents

1. Define in `agent_metadata`
2. Add to `role_tool_allowlist` with specific tools
3. Add to `role_tool_denylist` (explicit deny supercedes)
4. Add velocity limits to `velocity_config`
5. Add context rules if needed
6. Add tests in `test_opa_policies.py`
7. Run determinism test (10 identical requests)

### 9.2 Adding New Tools

1. Decide which agents can use it
2. Add to `role_tool_allowlist` for those agents
3. Add to `role_tool_denylist` for all others
4. If tool requires context, add to `tools_requiring_context`
5. Add context rules for each agent+tool
6. Set velocity limits
7. Add tests

### 9.3 Policy Updates

1. Update policy files in `policies/`
2. Validate syntax: `POST /api/opa/validate`
3. Run unit tests: `POST /api/opa/test`
4. Run integration tests: `pytest tests/test_opa_integration.py`
5. Verify determinism: Run same request 10 times
6. Deploy: Restart gateway with new policies

---

## Part 10: Quick Reference

| Decision | Rule File | Stage | Check |
|----------|-----------|-------|-------|
| "Can agent use tool?" | tool_rbac.rego | intent_binding | Tool in allowlist? |
| "Can agent use tool with this context?" | state_based_privilege.rego | state_privilege | Context allowed? |
| "Can agent make request now?" | resource_velocity.rego | velocity | Rate limit exceeded? |

| Default | Behavior |
|---------|----------|
| Allow | false (DENY) |
| Unknown Agent | false (DENY) |
| Unknown Tool | false (DENY) |
| OPA Unreachable | false (DENY) |
| Malformed Input | false (DENY) |

| Velocity Status | Action |
|-----------------|--------|
| hard_limit_exceeded | DENY |
| soft_limit_approaching | SANDBOX |
| ok | ALLOW |
| unknown | DENY |

---

**End of Documentation**
