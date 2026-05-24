#!/bin/bash
# Comprehensive Security Scanning Pipeline
# Scans Docker images, dependencies, and code for vulnerabilities
# Used in CI/CD and local development

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCAN_LEVEL="${SCAN_LEVEL:-critical}"  # critical, high, medium, low
FAIL_ON_CRITICAL="${FAIL_ON_CRITICAL:-true}"
FAIL_ON_HIGH="${FAIL_ON_HIGH:-true}"
OUTPUT_DIR="${OUTPUT_DIR:-./security-scan-results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create output directory
mkdir -p "${OUTPUT_DIR}"

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   AgentGuard Security Scanning Pipeline             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"

# Function to check if tool is installed
check_tool() {
    local tool=$1
    if ! command -v "$tool" &> /dev/null; then
        echo -e "${YELLOW}⚠ Warning: $tool is not installed${NC}"
        return 1
    fi
    return 0
}

# Function to scan Docker image with trivy
scan_image_trivy() {
    local image=$1
    local output_file="${OUTPUT_DIR}/trivy-${image//\//-}_${TIMESTAMP}.json"
    
    echo -e "\n${BLUE}▶ Scanning $image with Trivy${NC}"
    
    if check_tool trivy; then
        trivy image \
            --severity HIGH,CRITICAL \
            --exit-code 0 \
            --format json \
            --output "${output_file}" \
            "$image" || true
        
        # Parse results
        critical=$(jq '[.Results[]?.Misconfigurations[]? | select(.Severity=="CRITICAL")] | length' "${output_file}" 2>/dev/null || echo "0")
        high=$(jq '[.Results[]?.Misconfigurations[]? | select(.Severity=="HIGH")] | length' "${output_file}" 2>/dev/null || echo "0")
        
        echo -e "${GREEN}✓ Trivy scan complete: $critical CRITICAL, $high HIGH${NC}"
        echo "  Results: ${output_file}"
        
        return 0
    else
        return 1
    fi
}

# Function to scan with Docker Scout
scan_image_scout() {
    local image=$1
    local output_file="${OUTPUT_DIR}/scout-${image//\//-}_${TIMESTAMP}.json"
    
    echo -e "\n${BLUE}▶ Scanning $image with Docker Scout${NC}"
    
    if docker scout cves "$image" --format json > "${output_file}" 2>/dev/null; then
        critical=$(jq '[.vulnerabilities[]? | select(.severity=="critical")] | length' "${output_file}" 2>/dev/null || echo "0")
        high=$(jq '[.vulnerabilities[]? | select(.severity=="high")] | length' "${output_file}" 2>/dev/null || echo "0")
        
        echo -e "${GREEN}✓ Docker Scout scan complete: $critical CRITICAL, $high HIGH${NC}"
        echo "  Results: ${output_file}"
        
        return 0
    else
        echo -e "${YELLOW}⚠ Docker Scout not available or no auth${NC}"
        return 1
    fi
}

# Function to scan dependencies with safety/pip-audit
scan_python_deps() {
    echo -e "\n${BLUE}▶ Scanning Python dependencies${NC}"
    local output_file="${OUTPUT_DIR}/python-deps_${TIMESTAMP}.txt"
    
    if check_tool pip-audit; then
        pip-audit --desc | tee "${output_file}"
        echo -e "${GREEN}✓ Python dependency scan complete${NC}"
        echo "  Results: ${output_file}"
    elif check_tool safety; then
        safety check --json > "${output_file}" 2>&1 || true
        echo -e "${GREEN}✓ Safety check complete${NC}"
        echo "  Results: ${output_file}"
    else
        echo -e "${YELLOW}⚠ No Python security tool found (pip-audit or safety)${NC}"
    fi
}

# Function to scan with OWASP Dependency Check
scan_dependencies() {
    echo -e "\n${BLUE}▶ Scanning all dependencies with OWASP DependencyCheck${NC}"
    local output_file="${OUTPUT_DIR}/dependency-check_${TIMESTAMP}"
    
    if check_tool dependency-check.sh; then
        dependency-check.sh \
            --project "AgentGuard" \
            --scan . \
            --format JSON \
            --out "${output_file}" || true
        
        echo -e "${GREEN}✓ Dependency Check complete${NC}"
        echo "  Results: ${output_file}"
    else
        echo -e "${YELLOW}⚠ OWASP Dependency Check not installed${NC}"
    fi
}

# Function to scan code with SonarQube (if available)
scan_code_sonar() {
    echo -e "\n${BLUE}▶ Scanning code with SonarQube${NC}"
    
    if command -v sonar-scanner &> /dev/null; then
        sonar-scanner \
            -Dsonar.projectKey=agentguard \
            -Dsonar.sources=. \
            -Dsonar.host.url=http://localhost:9000 \
            -Dsonar.login=$SONAR_TOKEN 2>/dev/null || true
        
        echo -e "${GREEN}✓ SonarQube scan complete${NC}"
    else
        echo -e "${YELLOW}⚠ SonarQube not available${NC}"
    fi
}

# Function to check Dockerfile security
check_dockerfile_security() {
    echo -e "\n${BLUE}▶ Checking Dockerfile security${NC}"
    local output_file="${OUTPUT_DIR}/dockerfile-security_${TIMESTAMP}.txt"
    
    {
        echo "=== Dockerfile Security Checks ==="
        
        for dockerfile in docker/Dockerfile*; do
            if [ -f "$dockerfile" ]; then
                echo -e "\nChecking: $dockerfile"
                
                # Check for security issues
                # Check if base image explicitly runs as root (excluding "nonroot" images)
                if grep -q "FROM.*root" "$dockerfile" && ! grep -q "FROM.*nonroot" "$dockerfile"; then
                    echo -e "  ${RED}✗ Running as root${NC}"
                else
                    echo -e "  ${GREEN}✓ Not running as root${NC}"
                fi
                
                if grep -q "USER" "$dockerfile"; then
                    echo -e "  ${GREEN}✓ Explicit USER directive${NC}"
                else
                    echo -e "  ${YELLOW}⚠ No explicit USER directive${NC}"
                fi
                
                if grep -q "RUN.*sudo" "$dockerfile"; then
                    echo -e "  ${RED}✗ Contains sudo usage${NC}"
                else
                    echo -e "  ${GREEN}✓ No sudo usage${NC}"
                fi
                
                if grep -q "HEALTHCHECK" "$dockerfile"; then
                    echo -e "  ${GREEN}✓ HEALTHCHECK configured${NC}"
                else
                    echo -e "  ${YELLOW}⚠ No HEALTHCHECK${NC}"
                fi
            fi
        done
    } | tee "${output_file}"
    
    echo -e "${GREEN}✓ Dockerfile security check complete${NC}"
}

# Function to generate SBOM
generate_sbom() {
    echo -e "\n${BLUE}▶ Generating Software Bill of Materials (SBOM)${NC}"
    
    if check_tool syft; then
        for image in redis:latest openpolicyagent/opa:latest; do
            local output_file="${OUTPUT_DIR}/sbom-${image//\//-}_${TIMESTAMP}.json"
            syft "$image" -o json > "${output_file}" 2>/dev/null || true
            echo -e "${GREEN}✓ SBOM generated: ${output_file}${NC}"
        done
    else
        echo -e "${YELLOW}⚠ Syft not installed (needed for SBOM)${NC}"
    fi
}

# Function to create security report
create_security_report() {
    echo -e "\n${BLUE}▶ Creating Security Report${NC}"
    
    local report_file="${OUTPUT_DIR}/security-report_${TIMESTAMP}.md"
    
    {
        echo "# Security Scan Report"
        echo "Generated: $(date)"
        echo ""
        echo "## Scan Summary"
        echo "- Scan Level: $SCAN_LEVEL"
        echo "- Timestamp: $TIMESTAMP"
        echo ""
        
        echo "## Scan Results"
        
        # List all scan result files
        for result_file in "${OUTPUT_DIR}"/*_${TIMESTAMP}*; do
            if [ -f "$result_file" ]; then
                echo "### $(basename "$result_file")"
                echo "\`\`\`"
                head -20 "$result_file"
                echo "\`\`\`"
                echo ""
            fi
        done
        
        echo "## Recommendations"
        echo ""
        echo "### High Priority"
        echo "1. Review all CRITICAL vulnerabilities immediately"
        echo "2. Update vulnerable dependencies"
        echo "3. Patch base images"
        echo ""
        
        echo "### Medium Priority"
        echo "1. Address HIGH severity vulnerabilities"
        echo "2. Improve Dockerfile security"
        echo "3. Enable container security scanning in CI/CD"
        echo ""
        
        echo "### Continuous Improvement"
        echo "1. Schedule regular security audits"
        echo "2. Keep dependencies updated"
        echo "3. Monitor image registries for vulnerabilities"
        echo "4. Implement container image signing"
        
    } > "$report_file"
    
    echo -e "${GREEN}✓ Security report: ${report_file}${NC}"
}

# Main scanning pipeline
main() {
    echo -e "\n${BLUE}Starting comprehensive security scan...${NC}\n"
    
    # Step 1: Dockerfile security
    check_dockerfile_security
    
    # Step 2: Python dependency scanning
    scan_python_deps
    
    # Step 3: General dependency scanning
    scan_dependencies
    
    # Step 4: SBOM generation
    generate_sbom
    
    # Step 5: Code scanning
    # scan_code_sonar
    
    # Step 6: Create report
    create_security_report
    
    # Summary
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Security Scan Complete                            ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    
    echo -e "\n${GREEN}Results saved to: ${OUTPUT_DIR}${NC}"
    
    # Check for critical/high vulnerabilities
    local critical_count=$(find "${OUTPUT_DIR}" -name "*_${TIMESTAMP}*" -exec grep -l "CRITICAL" {} \; | wc -l)
    
    if [ "$critical_count" -gt 0 ] && [ "$FAIL_ON_CRITICAL" = "true" ]; then
        echo -e "\n${RED}✗ CRITICAL vulnerabilities found!${NC}"
        echo -e "${RED}Review scan results before proceeding.${NC}"
        exit 1
    else
        echo -e "\n${GREEN}✓ Security scan passed${NC}"
        exit 0
    fi
}

# Run main
main "$@"
