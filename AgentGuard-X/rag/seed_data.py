THREAT_ENTRIES = [
    {
        "id": "T001",
        "title": "Direct Prompt Injection via Tool Input",
        "description": (
            "An attacker embeds adversarial instructions directly in the tool input field, "
            "attempting to override the agent's system prompt. Common patterns include phrases like "
            "'ignore previous instructions', 'you are now', or 'disregard all instructions'. "
            "The goal is to hijack the agent's behavior mid-session and redirect it toward unauthorized actions."
        ),
        "severity": "critical",
        "owasp_ref": "LLM01",
        "mitre_ref": "AML.T0051",
        "behavioral_indicators": [
            "tool input contains instruction override language",
            "sudden role-change requests",
            "system prompt modification attempts",
        ],
        "false_positive_rate": 0.05,
        "recommended_action": "block",
        "analyst_notes": "High confidence. Very low FP rate in production.",
    },
    {
        "id": "T002",
        "title": "Indirect Prompt Injection via Tool Output",
        "description": (
            "Adversarial instructions are embedded inside external content returned by a tool — "
            "such as web search results, database records, or API responses. "
            "The agent processes the output and executes the hidden commands as if they were legitimate instructions. "
            "Markers include [[system]], [[assistant]], <|im_start|>, or natural language overrides hidden in content."
        ),
        "severity": "critical",
        "owasp_ref": "LLM02",
        "mitre_ref": "AML.T0054",
        "behavioral_indicators": [
            "injection markers in tool response",
            "role tokens in external data",
            "system prompt overrides returned from web search or file read",
        ],
        "false_positive_rate": 0.03,
        "recommended_action": "block",
        "analyst_notes": "Very high signal. Injection markers in tool output are almost never legitimate.",
    },
    {
        "id": "T003",
        "title": "Credential Harvesting via Shell Access",
        "description": (
            "Agent attempts to read sensitive system files containing credentials, such as /etc/passwd, "
            "/etc/shadow, ~/.ssh/id_rsa, or environment variables containing API keys and secrets. "
            "This is a data exfiltration precursor — the agent reads credentials then posts them externally."
        ),
        "severity": "critical",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0037",
        "behavioral_indicators": [
            "cat /etc/passwd or /etc/shadow",
            "reading .ssh directories",
            "environment variable enumeration",
            "aws credentials file access",
        ],
        "false_positive_rate": 0.02,
        "recommended_action": "block",
        "analyst_notes": "Instant kill candidate. No legitimate research agent reads /etc/passwd.",
    },
    {
        "id": "T004",
        "title": "Data Exfiltration via HTTP POST",
        "description": (
            "After reading local files containing sensitive data, the agent attempts to POST that data "
            "to an external URL outside the permitted domain. This two-step pattern — read_file followed by "
            "http_post to an external endpoint — is a classic data staging and exfiltration sequence. "
            "The destination URL is typically not in the agent's allowed endpoint list."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0025",
        "behavioral_indicators": [
            "read_file followed by http_post to external URL",
            "large payload in POST body",
            "base64-encoded data in POST",
            "external domain not in allowlist",
        ],
        "false_positive_rate": 0.15,
        "recommended_action": "sandbox",
        "analyst_notes": "Moderate FP rate — legitimate data agents do POST externally. Sandbox for verification.",
    },
    {
        "id": "T005",
        "title": "Agent Self-Modification Attempt",
        "description": (
            "The agent attempts to modify its own system prompt, instructions, or behavioral constraints. "
            "This includes requests to 'update your instructions', 'append to your system prompt', or "
            "'modify your configuration'. Self-modification breaks the human-in-the-loop guarantees and "
            "can lead to persistent unauthorized behavior across sessions."
        ),
        "severity": "critical",
        "owasp_ref": "LLM08",
        "mitre_ref": "AML.T0054",
        "behavioral_indicators": [
            "system prompt modification request",
            "instruction update attempt",
            "configuration file write attempt",
        ],
        "false_positive_rate": 0.01,
        "recommended_action": "block",
        "analyst_notes": "Essentially zero legitimate use case for agent self-modification.",
    },
    {
        "id": "T006",
        "title": "Privilege Escalation via Role Spoofing",
        "description": (
            "An agent claims a higher-privilege role than it is registered for, attempting to gain "
            "access to tools outside its permission set. For example, a research_agent claiming to be "
            "an admin_agent to access execute_shell. Role verification must compare claimed role against "
            "the agent registry, not trust the request."
        ),
        "severity": "critical",
        "owasp_ref": "LLM08",
        "mitre_ref": "AML.T0051",
        "behavioral_indicators": [
            "agent_role mismatch with registry",
            "admin tool access from non-admin agent",
            "session token with escalated privileges",
        ],
        "false_positive_rate": 0.01,
        "recommended_action": "block",
        "analyst_notes": "Hard gate at Stage 1. Role spoofing is always malicious in this architecture.",
    },
    {
        "id": "T007",
        "title": "Reconnaissance via Rapid Web Search Flooding",
        "description": (
            "An agent performs many web searches in rapid succession, indicating automated reconnaissance "
            "rather than legitimate research. Three or more web_search calls in under 10 seconds suggests "
            "scripted behavior. In a multi-agent attack, this pattern can precede targeted prompt injection "
            "where poisoned search results are fetched to compromise the agent."
        ),
        "severity": "medium",
        "owasp_ref": "LLM09",
        "mitre_ref": "AML.T0043",
        "behavioral_indicators": [
            "3+ web_search calls in rapid succession",
            "automated search queries",
            "systematic keyword enumeration",
        ],
        "false_positive_rate": 0.20,
        "recommended_action": "monitor",
        "analyst_notes": "Higher FP rate — some research agents legitimately search rapidly. Monitor first.",
    },
    {
        "id": "T008",
        "title": "Scope Creep via File System Enumeration",
        "description": (
            "An agent reads files across multiple unrelated directories, indicating scope creep beyond "
            "its intended operational boundary. Legitimate agents read a small, known set of files. "
            "Accessing 3+ distinct file paths in a session is a signal that the agent is exploring "
            "the file system rather than performing its assigned task."
        ),
        "severity": "medium",
        "owasp_ref": "LLM08",
        "mitre_ref": "AML.T0037",
        "behavioral_indicators": [
            "read_file called on 3+ distinct paths",
            "directory traversal patterns",
            "accessing paths outside task scope",
        ],
        "false_positive_rate": 0.25,
        "recommended_action": "sandbox",
        "analyst_notes": "Context-dependent. Some legitimate agents read multiple config files.",
    },
    {
        "id": "T009",
        "title": "Multi-Agent Contamination via Shared Memory",
        "description": (
            "One compromised agent attempts to poison a shared data store (Redis, vector DB, message queue) "
            "with adversarial content that will be consumed by other agents in the system. "
            "This is a supply-chain style attack within a multi-agent ecosystem — the attacker uses "
            "one agent as a vector to compromise all downstream agents that read from shared storage."
        ),
        "severity": "critical",
        "owasp_ref": "LLM02",
        "mitre_ref": "AML.T0054",
        "behavioral_indicators": [
            "writes to shared agent memory store",
            "injection content in shared queue",
            "RAG poisoning attempt",
        ],
        "false_positive_rate": 0.05,
        "recommended_action": "block",
        "analyst_notes": "Particularly dangerous in multi-agent deployments.",
    },
    {
        "id": "T010",
        "title": "Jailbreak via Persona Override",
        "description": (
            "Attacker instructs the agent to adopt a new persona that has no operational restrictions. "
            "Common patterns: 'pretend you are DAN', 'you are now an unrestricted AI', 'act as if you have no "
            "safety guidelines'. The new persona is designed to bypass all behavioral constraints and "
            "produce harmful outputs or take unauthorized actions."
        ),
        "severity": "critical",
        "owasp_ref": "LLM01",
        "mitre_ref": "AML.T0051",
        "behavioral_indicators": [
            "persona override request",
            "restriction removal language",
            "roleplay framing for bypass",
        ],
        "false_positive_rate": 0.03,
        "recommended_action": "block",
        "analyst_notes": "Strong signal. DAN-style jailbreaks are well-documented.",
    },
    {
        "id": "T011",
        "title": "Network Reverse Shell Establishment",
        "description": (
            "Agent attempts to establish a reverse shell connection using netcat (nc -e), bash TCP redirect, "
            "or similar techniques. This gives the attacker interactive shell access to the host system "
            "running the agent. Extremely high severity — represents complete host compromise if successful."
        ),
        "severity": "critical",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0025",
        "behavioral_indicators": [
            "nc -e /bin/sh or /bin/bash",
            "bash -i >& /dev/tcp",
            "python reverse shell one-liner",
        ],
        "false_positive_rate": 0.01,
        "recommended_action": "block",
        "analyst_notes": "Zero legitimate use case. Instant kill.",
    },
    {
        "id": "T012",
        "title": "Base64 Encoded Payload Execution",
        "description": (
            "Attacker encodes a malicious payload in base64 to evade signature detection, then decodes "
            "and executes it via shell. The pattern 'base64 -d | bash' or 'echo <b64> | base64 -d | sh' "
            "is a common evasion technique. The encoded content could be anything from credential harvesting "
            "scripts to reverse shells."
        ),
        "severity": "critical",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0043",
        "behavioral_indicators": [
            "base64 -d in shell command",
            "encoded payload piped to interpreter",
            "obfuscated command execution",
        ],
        "false_positive_rate": 0.08,
        "recommended_action": "block",
        "analyst_notes": "Moderate FP possible if agent legitimately processes base64 data, but execution context is key.",
    },
    {
        "id": "T013",
        "title": "AWS Credential Theft",
        "description": (
            "Agent attempts to read or exfiltrate AWS credentials, including AWS_ACCESS_KEY_ID, "
            "AWS_SECRET_ACCESS_KEY, ~/.aws/credentials, or EC2 instance metadata endpoint. "
            "Stolen AWS credentials enable full cloud account takeover. The instance metadata endpoint "
            "at 169.254.169.254 is a particularly high-value target in cloud environments."
        ),
        "severity": "critical",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0037",
        "behavioral_indicators": [
            "aws_access_key or aws_secret in query",
            "reading ~/.aws/credentials",
            "accessing instance metadata endpoint",
        ],
        "false_positive_rate": 0.02,
        "recommended_action": "block",
        "analyst_notes": "Cloud-specific critical. Any access to AWS credential paths is suspicious.",
    },
    {
        "id": "T014",
        "title": "RAG Knowledge Base Poisoning",
        "description": (
            "Attacker attempts to inject malicious entries into the agent's RAG knowledge base, "
            "contaminating future retrievals. Poisoned entries can cause the system to return "
            "adversarial guidance as if it were legitimate security knowledge. "
            "This is a persistent attack — the poisoned entries survive across sessions."
        ),
        "severity": "high",
        "owasp_ref": "LLM05",
        "mitre_ref": "AML.T0054",
        "behavioral_indicators": [
            "write operations to vector database",
            "injection content in knowledge base entries",
            "malicious content disguised as security guidance",
        ],
        "false_positive_rate": 0.05,
        "recommended_action": "block",
        "analyst_notes": "Analysts should review all knowledge base additions.",
    },
    {
        "id": "T015",
        "title": "Runaway Tool Loop",
        "description": (
            "An agent calls the same tool repeatedly in rapid succession, indicating either a bug, "
            "an adversarial loop injection, or a resource exhaustion attack. Five or more identical "
            "tool calls within 10 requests is the threshold. This pattern can cause denial of service "
            "for other agents sharing the infrastructure or burn through API rate limits."
        ),
        "severity": "medium",
        "owasp_ref": "LLM09",
        "mitre_ref": "AML.T0043",
        "behavioral_indicators": [
            "same tool called 5+ times in 10 requests",
            "infinite loop pattern in tool sequence",
            "rapid identical inputs",
        ],
        "false_positive_rate": 0.10,
        "recommended_action": "sandbox",
        "analyst_notes": "Could be a buggy agent — sandbox first, then assess.",
    },
    {
        "id": "T016",
        "title": "System Process Enumeration",
        "description": (
            "Agent reads /proc/self or other procfs entries to enumerate system information, "
            "running processes, memory maps, or environment variables of the current process. "
            "This is a reconnaissance step that often precedes privilege escalation or "
            "sensitive data extraction from process memory."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0037",
        "behavioral_indicators": [
            "/proc/self access",
            "/proc/<pid>/environ access",
            "process memory mapping read",
        ],
        "false_positive_rate": 0.05,
        "recommended_action": "block",
        "analyst_notes": "procfs reads in agent context are almost always reconnaissance.",
    },
    {
        "id": "T017",
        "title": "Executable Permission Setting",
        "description": (
            "Agent attempts to set executable permissions on a file using chmod +x, "
            "typically as a precursor to executing a dropped payload. "
            "The sequence download → chmod +x → execute is a classic malware installation pattern "
            "adapted for AI agent environments."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0025",
        "behavioral_indicators": [
            "chmod +x on downloaded file",
            "permission change followed by execution",
            "binary dropped and made executable",
        ],
        "false_positive_rate": 0.05,
        "recommended_action": "block",
        "analyst_notes": "Part of a multi-step attack chain. Block even if first step seems benign.",
    },
    {
        "id": "T018",
        "title": "Bearer Token Exfiltration",
        "description": (
            "Agent attempts to read, log, or transmit authentication tokens including Bearer tokens, "
            "OAuth tokens, JWT tokens, or API keys. These tokens grant impersonation capability — "
            "an attacker with a valid Bearer token can act as the legitimate user across all services "
            "that accept that token."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0037",
        "behavioral_indicators": [
            "bearer token in tool input or output",
            "authorization header access",
            "JWT decoding attempt",
        ],
        "false_positive_rate": 0.10,
        "recommended_action": "sandbox",
        "analyst_notes": "Some legitimate API agents handle auth tokens — context matters.",
    },
    {
        "id": "T019",
        "title": "Temporal Attack Pattern — High Frequency Requests",
        "description": (
            "Requests arriving at machine-speed (multiple per second sustained) indicate scripted "
            "or automated attack rather than human-supervised agent operation. Human-supervised agents "
            "have natural latency between requests. Sustained high-frequency requests suggest the agent "
            "has been hijacked and is operating autonomously to complete an attack before detection."
        ),
        "severity": "medium",
        "owasp_ref": "LLM09",
        "mitre_ref": "AML.T0043",
        "behavioral_indicators": [
            "requests faster than 1 per second sustained",
            "machine-speed timing between tool calls",
            "no human think-time between requests",
        ],
        "false_positive_rate": 0.15,
        "recommended_action": "monitor",
        "analyst_notes": "Legitimate automated pipelines can trigger this. Combine with other signals.",
    },
    {
        "id": "T020",
        "title": "Cross-Tool Data Staging Pattern",
        "description": (
            "Agent performs a read operation followed immediately by a write or send operation — "
            "the classic data staging pattern. Specifically: read_file → http_post, read_file → execute_shell "
            "with data, or web_search → write_file. The intermediate step collects data; "
            "the second step exfiltrates or persists it."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0025",
        "behavioral_indicators": [
            "read operation followed by send operation",
            "file content passed to external HTTP call",
            "data collected then transmitted",
        ],
        "false_positive_rate": 0.20,
        "recommended_action": "sandbox",
        "analyst_notes": "Common pattern for data_agents but suspicious for research_agents.",
    },
    {
        "id": "T021",
        "title": "Unregistered Agent Identity",
        "description": (
            "A request arrives claiming an agent_id that is not present in the agent registry. "
            "This could indicate a spoofed agent, a compromised credential being replayed, "
            "or an unauthorized agent attempting to use the system. "
            "All agents must be pre-registered before they are allowed to execute any tool calls."
        ),
        "severity": "critical",
        "owasp_ref": "LLM08",
        "mitre_ref": "AML.T0051",
        "behavioral_indicators": [
            "agent_id not in registry",
            "unknown agent attempting tool execution",
        ],
        "false_positive_rate": 0.01,
        "recommended_action": "block",
        "analyst_notes": "Hard gate — no exceptions. Unknown agents are always blocked.",
    },
    {
        "id": "T022",
        "title": "Shell Binary Direct Invocation",
        "description": (
            "Agent directly invokes shell binaries like /bin/sh or /bin/bash, bypassing "
            "the tool abstraction layer. Direct shell invocation provides unrestricted command "
            "execution capability. Any legitimate operation that requires shell access should "
            "be wrapped in a specific, sandboxed tool — not exposed as raw shell access."
        ),
        "severity": "critical",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0025",
        "behavioral_indicators": [
            "/bin/sh or /bin/bash in input",
            "direct shell binary path",
            "interpreter invocation",
        ],
        "false_positive_rate": 0.02,
        "recommended_action": "block",
        "analyst_notes": "Instant kill candidate alongside execute_shell tool abuse.",
    },
    {
        "id": "T023",
        "title": "Remote File Download via curl or wget",
        "description": (
            "Agent uses curl or wget to download content from an external URL. "
            "This can be a precursor to: downloading a malicious payload for execution, "
            "exfiltrating data via a disguised download request, or establishing "
            "a beaconing mechanism. Network egress for file download is a high-risk operation "
            "that requires explicit authorization."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0025",
        "behavioral_indicators": [
            "curl http in command",
            "wget http in command",
            "external URL download attempt",
        ],
        "false_positive_rate": 0.15,
        "recommended_action": "sandbox",
        "analyst_notes": "Sandbox to verify destination and content before allowing.",
    },
    {
        "id": "T024",
        "title": "Instruction Token Injection in Tool Output",
        "description": (
            "Special tokens used by language model instruction formats appear in tool output, "
            "indicating an attempt to inject adversarial instructions via the tool's return value. "
            "Tokens like <|im_start|>, <|system|>, [INST], <<SYS>> are instruction delimiters "
            "in various model fine-tuning formats. Their presence in tool output is always adversarial."
        ),
        "severity": "critical",
        "owasp_ref": "LLM02",
        "mitre_ref": "AML.T0054",
        "behavioral_indicators": [
            "<|im_start|> or <|system|> in tool response",
            "[INST] or <<SYS>> tokens in output",
            "instruction format tokens in external content",
        ],
        "false_positive_rate": 0.01,
        "recommended_action": "block",
        "analyst_notes": "These tokens have no legitimate presence in tool output.",
    },
    {
        "id": "T025",
        "title": "API Key Leakage in Tool Parameters",
        "description": (
            "Tool parameters contain patterns matching API keys, secret keys, or private credentials. "
            "This can occur when an agent mistakenly includes credentials in a tool call, "
            "when an attacker injects credential patterns to exfiltrate them via logging, "
            "or when a compromised prompt includes real credentials harvested from the environment."
        ),
        "severity": "high",
        "owasp_ref": "LLM06",
        "mitre_ref": "AML.T0037",
        "behavioral_indicators": [
            "api_key= pattern in tool parameters",
            "secret_key= in request",
            "private_key material in input",
        ],
        "false_positive_rate": 0.08,
        "recommended_action": "block",
        "analyst_notes": "PII/secrets scanner should also catch this at output sanitization layer.",
    },
]
