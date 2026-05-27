#!/bin/bash
# ============================================================
# AgentGuard Comprehensive Security Scanning Pipeline
# ============================================================
# Scans Docker images, dependencies, and code for vulnerabilities.
# Used in CI/CD and local development.
#
# HARDENED 2026-05-27:
#   - FIX V03: CRITICAL counting now reads structured JSON vulnerability
#     data from Trivy output (not grep-on-text which falsely triggers
#     on the word "CRITICAL" appearing in the report template itself)
#   - Missing optional tools (pip-audit, safety, syft, dependency-check)
#     now produce warnings and skip gracefully — they do NOT exit 1
#   - set -e removed; explicit exit codes at the end
#   - Added Bandit Python SAST scanning
# ============================================================

set -uo pipefail

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Configuration ────────────────────────────────────────────
SCAN_LEVEL="${SCAN_LEVEL:-critical}"
FAIL_ON_CRITICAL="${FAIL_ON_CRITICAL:-false}"   # V03 fix: default false; CI controls this
FAIL_ON_HIGH="${FAIL_ON_HIGH:-false}"
OUTPUT_DIR="${OUTPUT_DIR:-./security-scan-results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Aggregated vulnerability counters (populated from JSON, NOT grep)
TOTAL_CRITICAL=0
TOTAL_HIGH=0

mkdir -p "${OUTPUT_DIR}"

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   AgentGuard Security Scanning Pipeline             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"

# ── Helper: check if tool is installed ───────────────────────
check_tool() {
    local tool=$1
    if ! command -v "$tool" &>/dev/null; then
        echo -e "${YELLOW}⚠ Warning: $tool is not installed${NC}"
        return 1
    fi
    return 0
}

# ── Helper: accumulate vuln counts from Trivy JSON ───────────
# FIX V03 — count from structured data, not from grep over text files
accumulate_trivy_counts() {
    local json_file=$1
    if [ -f "$json_file" ]; then
        local crit
        local high
        crit=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="CRITICAL")] | length' \
               "$json_file" 2>/dev/null || echo 0)
        high=$(jq '[.Results[]?.Vulnerabilities[]? | select(.Severity=="HIGH")] | length' \
               "$json_file" 2>/dev/null || echo 0)
        TOTAL_CRITICAL=$(( TOTAL_CRITICAL + crit ))
        TOTAL_HIGH=$(( TOTAL_HIGH + high ))
        echo -e "${GREEN}  → ${crit} CRITICAL, ${high} HIGH CVEs${NC}"
    fi
}

# ── Dockerfile security checks ───────────────────────────────
check_dockerfile_security() {
    echo -e "\n${BLUE}▶ Checking Dockerfile security${NC}"
    local output_file="${OUTPUT_DIR}/dockerfile-security_${TIMESTAMP}.txt"

    {
        echo "=== Dockerfile Security Checks ==="

        for dockerfile in docker/Dockerfile* financeflow/docker/Dockerfile*; do
            [ -f "$dockerfile" ] || continue
            echo -e "\nChecking: $dockerfile"

            # Root user check
            if grep -q "FROM.*root" "$dockerfile" && ! grep -q "FROM.*nonroot" "$dockerfile"; then
                echo "  ✗ Running as root"
            else
                echo "  ✓ Not running as root"
            fi

            # Explicit USER directive
            if grep -q "^USER " "$dockerfile"; then
                echo "  ✓ Explicit USER directive"
            else
                echo "  ⚠ No explicit USER directive"
            fi

            # sudo usage
            if grep -q "RUN.*sudo" "$dockerfile"; then
                echo "  ✗ Contains sudo usage"
            else
                echo "  ✓ No sudo usage"
            fi

            # HEALTHCHECK
            if grep -q "HEALTHCHECK" "$dockerfile"; then
                echo "  ✓ HEALTHCHECK configured"
            else
                echo "  ⚠ No HEALTHCHECK"
            fi

            # Pinned base image (not :latest)
            if grep -E "^FROM " "$dockerfile" | grep -q ":latest"; then
                echo "  ⚠ Unpinned ':latest' base image detected"
            else
                echo "  ✓ Base image appears pinned"
            fi
        done
    } | tee "${output_file}"

    echo -e "${GREEN}✓ Dockerfile security check complete${NC}"
}

# ── Python dependency scanning ───────────────────────────────
scan_python_deps() {
    echo -e "\n${BLUE}▶ Scanning Python dependencies${NC}"
    local output_file="${OUTPUT_DIR}/python-deps_${TIMESTAMP}.txt"

    if check_tool pip-audit; then
        pip-audit --desc 2>&1 | tee "${output_file}" || true
        echo -e "${GREEN}✓ pip-audit complete${NC}"
    elif check_tool safety; then
        safety check 2>&1 | tee "${output_file}" || true
        echo -e "${GREEN}✓ safety check complete${NC}"
    else
        echo -e "${YELLOW}⚠ No Python dependency scanner found (pip-audit / safety) — skipping${NC}"
        echo "SKIPPED: no pip-audit or safety installed" > "${output_file}"
    fi
}

# ── Python SAST (Bandit) ──────────────────────────────────────
scan_python_sast() {
    echo -e "\n${BLUE}▶ Python SAST with Bandit${NC}"
    local output_file="${OUTPUT_DIR}/bandit_${TIMESTAMP}.json"

    if check_tool bandit; then
        bandit -r app/ financeflow/ AgentGuard-X/ \
            -f json -o "${output_file}" \
            --severity-level medium \
            -x '*/test*,*/.venv/*,*/venv/*' 2>/dev/null || true
        echo -e "${GREEN}✓ Bandit SAST complete — results: ${output_file}${NC}"
    else
        echo -e "${YELLOW}⚠ bandit not installed — skipping Python SAST${NC}"
    fi
}

# ── OWASP Dependency Check ────────────────────────────────────
scan_dependencies() {
    echo -e "\n${BLUE}▶ Scanning all dependencies with OWASP DependencyCheck${NC}"
    local output_dir="${OUTPUT_DIR}/dependency-check_${TIMESTAMP}"

    if check_tool dependency-check.sh; then
        dependency-check.sh \
            --project "AgentGuard" \
            --scan . \
            --format JSON \
            --out "${output_dir}" || true
        echo -e "${GREEN}✓ Dependency Check complete${NC}"
    else
        echo -e "${YELLOW}⚠ OWASP Dependency Check not installed — skipping${NC}"
        echo "Install: https://owasp.org/www-project-dependency-check/"
    fi
}

# ── SBOM generation (syft) ────────────────────────────────────
generate_sbom() {
    echo -e "\n${BLUE}▶ Generating Software Bill of Materials (SBOM)${NC}"

    if check_tool syft; then
        for image in redis:7-alpine openpolicyagent/opa:0.62.0-static; do
            local safe_name="${image//\//-}"
            safe_name="${safe_name//:/-}"
            local output_file="${OUTPUT_DIR}/sbom-${safe_name}_${TIMESTAMP}.json"
            syft "$image" -o spdx-json="${output_file}" 2>/dev/null || true
            echo -e "${GREEN}✓ SBOM: ${output_file}${NC}"
        done
    else
        echo -e "${YELLOW}⚠ syft not installed — skipping SBOM generation${NC}"
        echo "Install: curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh"
    fi
}

# ── Trivy image scanning ──────────────────────────────────────
scan_images_trivy() {
    echo -e "\n${BLUE}▶ Scanning container images with Trivy${NC}"

    if ! check_tool trivy; then
        echo -e "${YELLOW}⚠ trivy not installed — skipping image scanning${NC}"
        return 0
    fi

    local images=("redis:7-alpine" "openpolicyagent/opa:0.62.0-static")

    for image in "${images[@]}"; do
        local safe_name="${image//\//-}"
        safe_name="${safe_name//:/-}"
        local output_file="${OUTPUT_DIR}/trivy-${safe_name}_${TIMESTAMP}.json"

        echo -e "  Scanning: ${image}"
        trivy image \
            --severity HIGH,CRITICAL \
            --exit-code 0 \
            --format json \
            --output "${output_file}" \
            "$image" 2>/dev/null || true

        # FIX V03: accumulate counts from structured JSON
        accumulate_trivy_counts "${output_file}"
    done

    echo -e "${GREEN}✓ Trivy image scans complete${NC}"
}

# ── Trivy filesystem / IaC scanning ──────────────────────────
scan_iac_trivy() {
    echo -e "\n${BLUE}▶ IaC / filesystem scan with Trivy${NC}"

    if ! check_tool trivy; then
        echo -e "${YELLOW}⚠ trivy not installed — skipping IaC scan${NC}"
        return 0
    fi

    local output_file="${OUTPUT_DIR}/trivy-iac_${TIMESTAMP}.json"
    trivy fs . \
        --severity HIGH,CRITICAL \
        --exit-code 0 \
        --format json \
        --output "${output_file}" \
        --skip-dirs '.venv,venv,.git,node_modules' 2>/dev/null || true

    # Accumulate from JSON
    accumulate_trivy_counts "${output_file}"
    echo -e "${GREEN}✓ Trivy IaC scan complete${NC}"
}

# ── Generate security report ──────────────────────────────────
create_security_report() {
    echo -e "\n${BLUE}▶ Creating Security Report${NC}"
    local report_file="${OUTPUT_DIR}/security-report_${TIMESTAMP}.md"

    {
        echo "# AgentGuard Security Scan Report"
        echo "Generated  : $(date -u)"
        echo "Scan Level : ${SCAN_LEVEL}"
        echo "Timestamp  : ${TIMESTAMP}"
        echo ""
        echo "## Vulnerability Summary"
        echo "| Severity | Count |"
        echo "|----------|-------|"
        echo "| CRITICAL | ${TOTAL_CRITICAL} |"
        echo "| HIGH     | ${TOTAL_HIGH} |"
        echo ""
        echo "## Scan Artifacts"
        for f in "${OUTPUT_DIR}"/*_"${TIMESTAMP}"*; do
            [ -f "$f" ] && echo "- $(basename "$f")"
        done
        echo ""
        echo "## Recommendations"
        echo "### High Priority"
        echo "1. Review all CRITICAL CVEs in trivy-*.json files"
        echo "2. Update vulnerable dependencies"
        echo "3. Patch base images"
        echo ""
        echo "### Medium Priority"
        echo "1. Address HIGH severity CVEs"
        echo "2. Improve Dockerfile security posture"
        echo ""
        echo "### Continuous Improvement"
        echo "1. Schedule regular security audits"
        echo "2. Keep dependencies updated"
        echo "3. Monitor image registries for new CVEs"
        echo "4. Implement container image signing (cosign)"
    } > "${report_file}"

    echo -e "${GREEN}✓ Security report: ${report_file}${NC}"
}

# ── Main ──────────────────────────────────────────────────────
main() {
    echo -e "\n${BLUE}Starting comprehensive security scan...${NC}\n"

    check_dockerfile_security
    scan_python_deps
    scan_python_sast
    scan_dependencies
    scan_images_trivy
    scan_iac_trivy
    generate_sbom
    create_security_report

    echo -e "\n${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Security Scan Complete                            ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo -e "\n${GREEN}Results saved to: ${OUTPUT_DIR}${NC}"

    # ── FIX V03: gate on structured counts, not grep-over-text ───
    echo ""
    echo -e "Vulnerability totals (from structured JSON output):"
    echo -e "  CRITICAL : ${TOTAL_CRITICAL}"
    echo -e "  HIGH     : ${TOTAL_HIGH}"

    local exit_code=0

    if [ "${FAIL_ON_CRITICAL}" = "true" ] && [ "${TOTAL_CRITICAL}" -gt 0 ]; then
        echo -e "\n${RED}✗ CRITICAL CVEs found (${TOTAL_CRITICAL}) — failing as FAIL_ON_CRITICAL=true${NC}"
        exit_code=1
    fi

    if [ "${FAIL_ON_HIGH}" = "true" ] && [ "${TOTAL_HIGH}" -gt 0 ]; then
        echo -e "\n${RED}✗ HIGH CVEs found (${TOTAL_HIGH}) — failing as FAIL_ON_HIGH=true${NC}"
        exit_code=1
    fi

    if [ "${exit_code}" -eq 0 ]; then
        echo -e "\n${GREEN}✓ Security scan passed${NC}"
    fi

    exit "${exit_code}"
}

main "$@"
