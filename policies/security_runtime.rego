# OPA Security Policy - Runtime Security Enforcement
# Implements: Container security, network policies, capability restrictions

package security

# ============================================================================
# CONTAINER SECURITY POLICIES
# ============================================================================

# Policy: Deny containers running as root
deny_root_container[msg] {
    input.container.user == "root"
    msg := "SECURITY_VIOLATION: Container running as root. Must run as non-root user."
}

# Policy: Enforce read-only root filesystem
deny_writable_root_fs[msg] {
    not input.container.read_only_root_fs
    msg := "SECURITY_VIOLATION: Root filesystem is writable. Must use read-only root filesystem."
}

# Policy: Require capability dropping
deny_without_cap_drop[msg] {
    not input.container.security_context.capabilities.drop
    msg := "SECURITY_VIOLATION: Capabilities not dropped. Must drop unnecessary capabilities."
}

# Policy: Enforce privilege mode disabled
deny_privileged_mode[msg] {
    input.container.security_context.privileged == true
    msg := "SECURITY_VIOLATION: Container runs in privileged mode. Must disable privileged mode."
}

# Policy: Deny escape allow
deny_allow_privilege_escalation[msg] {
    input.container.security_context.allow_privilege_escalation == true
    msg := "SECURITY_VIOLATION: Privilege escalation allowed. Must disable allow_privilege_escalation."
}

# Policy: Enforce resource limits
deny_no_resource_limits[msg] {
    not input.container.resources.limits.memory
    msg := "SECURITY_VIOLATION: Memory limit not set. Must set memory resource limit."
}

deny_no_cpu_limits[msg] {
    not input.container.resources.limits.cpu
    msg := "SECURITY_VIOLATION: CPU limit not set. Must set CPU resource limit."
}

# Policy: Enforce security scanning
deny_unscanned_images[msg] {
    input.container.image_security_status != "scanned_clean"
    msg := "SECURITY_VIOLATION: Image not scanned or has vulnerabilities. Use scanned images only."
}

# Policy: Require security labels
deny_missing_security_labels[msg] {
    not input.container.labels["security.level"]
    msg := "SECURITY_VIOLATION: Security level label missing. Containers must be labeled."
}

# ============================================================================
# NETWORK POLICIES
# ============================================================================

# Policy: Enforce network policies
deny_no_network_policy[msg] {
    not input.network.policy_enabled
    msg := "SECURITY_VIOLATION: Network policy not enabled. Must enforce network policies."
}

# Policy: Restrict inter-container communication
allow_network_traffic[decision] {
    input.network.from_pod in ["gateway", "opa", "redis"]
    input.network.to_pod in ["gateway", "opa", "redis"]
    input.network.from_pod != input.network.to_pod
    
    # Allow specific connections
    allowed_paths := {
        "gateway": ["opa", "redis"],
        "opa": ["redis"],
        "redis": []
    }
    
    input.network.to_pod in allowed_paths[input.network.from_pod]
    decision := "allow"
}

# Policy: Deny unexpected network traffic
deny_unexpected_network[msg] {
    not allow_network_traffic
    msg := sprintf("SECURITY_VIOLATION: Unauthorized network traffic from %s to %s", [input.network.from_pod, input.network.to_pod])
}

# ============================================================================
# AUTHENTICATION & AUTHORIZATION
# ============================================================================

# Policy: Require MTLS for inter-service communication
deny_no_mtls[msg] {
    input.communication.service_to_service
    not input.communication.mtls_enabled
    msg := "SECURITY_VIOLATION: MTLS not enabled for service-to-service communication. Must use mTLS."
}

# Policy: Enforce certificate validation
deny_cert_validation_disabled[msg] {
    not input.tls.verify_peer
    msg := "SECURITY_VIOLATION: Certificate verification disabled. Must verify peer certificates."
}

# Policy: Require strong cipher suites
deny_weak_ciphers[msg] {
    input.tls.cipher_suite in ["TLS_RSA_WITH_AES_128_CBC_SHA", "TLS_RSA_WITH_RC4_128_SHA"]
    msg := sprintf("SECURITY_VIOLATION: Weak cipher suite %s detected. Must use strong ciphers.", [input.tls.cipher_suite])
}

# ============================================================================
# SECRETS & CREDENTIALS MANAGEMENT
# ============================================================================

# Policy: Deny hardcoded secrets
deny_hardcoded_secrets[msg] {
    contains(input.code, "password=")
    msg := "SECURITY_VIOLATION: Hardcoded password detected. Use secrets management."
}

deny_hardcoded_api_keys[msg] {
    contains(input.code, "api_key=")
    msg := "SECURITY_VIOLATION: Hardcoded API key detected. Use secrets management."
}

# Policy: Require secret encryption
deny_unencrypted_secrets[msg] {
    input.secrets.encryption != "enabled"
    msg := "SECURITY_VIOLATION: Secrets not encrypted. Must enable secret encryption."
}

# ============================================================================
# LOGGING & AUDIT
# ============================================================================

# Policy: Enforce audit logging
deny_no_audit_logging[msg] {
    not input.logging.audit_enabled
    msg := "SECURITY_VIOLATION: Audit logging not enabled. Must enable audit logs."
}

# Policy: Require JSON structured logging
deny_unstructured_logging[msg] {
    input.logging.format != "json"
    msg := "SECURITY_VIOLATION: Logging not in JSON format. Must use structured JSON logging."
}

# Policy: Enforce log retention
deny_no_log_retention[msg] {
    not input.logging.retention_days
    msg := "SECURITY_VIOLATION: Log retention not configured. Must configure log retention."
}

# ============================================================================
# VULNERABILITIES & COMPLIANCE
# ============================================================================

# Policy: Deny high/critical vulnerabilities
deny_vulnerable_image[msg] {
    input.image.vulnerabilities.critical > 0
    msg := sprintf("SECURITY_VIOLATION: Image has %d CRITICAL vulnerabilities.", [input.image.vulnerabilities.critical])
}

deny_vulnerable_high[msg] {
    input.image.vulnerabilities.high > 10
    msg := sprintf("SECURITY_VIOLATION: Image has %d HIGH vulnerabilities.", [input.image.vulnerabilities.high])
}

# Policy: Enforce image signing
deny_unsigned_image[msg] {
    not input.image.signed
    msg := "SECURITY_VIOLATION: Container image not signed. Must use signed images."
}

# ============================================================================
# AGGREGATE SECURITY DECISION
# ============================================================================

# Collect all security violations
all_violations[violation] {
    violation := v
    v := deny_root_container[_]
}

all_violations[violation] {
    violation := v
    v := deny_writable_root_fs[_]
}

all_violations[violation] {
    violation := v
    v := deny_without_cap_drop[_]
}

all_violations[violation] {
    violation := v
    v := deny_privileged_mode[_]
}

all_violations[violation] {
    violation := v
    v := deny_allow_privilege_escalation[_]
}

all_violations[violation] {
    violation := v
    v := deny_no_resource_limits[_]
}

all_violations[violation] {
    violation := v
    v := deny_no_cpu_limits[_]
}

all_violations[violation] {
    violation := v
    v := deny_unscanned_images[_]
}

all_violations[violation] {
    violation := v
    v := deny_missing_security_labels[_]
}

# Final security decision
allow_deployment {
    not any_violations
}

any_violations if {
    count(all_violations) > 0
}

# Determine severity level
severity_level := "CRITICAL" if any_violations else "CLEAR"

# Security summary
security_summary := {
    "total_violations": count(all_violations),
    "violations": all_violations,
    "allows_deployment": allow_deployment,
    "severity_level": severity_level
}
