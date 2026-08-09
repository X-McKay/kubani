#!/bin/bash
# Comprehensive cluster validation script
# Validates all services, DNS, connectivity, and Kubernetes resources
# Usage: ./scripts/validate_cluster.sh [--quick|--full|--json]
#
# Exit codes:
#   0 - All checks passed
#   1 - One or more checks failed
#   2 - Critical failure (cluster unreachable)

set -e

# Colors (disabled in JSON mode)
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Parse arguments
MODE="standard"
JSON_OUTPUT=false
for arg in "$@"; do
    case $arg in
        --quick) MODE="quick" ;;
        --full) MODE="full" ;;
        --json) JSON_OUTPUT=true ;;
    esac
done

# Disable colors in JSON mode
if [ "$JSON_OUTPUT" = true ]; then
    GREEN='' RED='' YELLOW='' BLUE='' CYAN='' NC=''
fi

# Results tracking
declare -A RESULTS
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# Track failures for JSON output
FAILURES=()
WARNINGS_LIST=()

# Helper functions
log() {
    if [ "$JSON_OUTPUT" = false ]; then
        # Support `log -n "..."` for same-line labels. Without this the -n was
        # consumed as $1 and `echo -e "-n"` printed nothing at all, which is why
        # every check used to render as a bare checkmark with no service name.
        if [ "$1" = "-n" ]; then
            shift
            echo -e -n "$1"
        else
            echo -e "$1"
        fi
    fi
}

record_result() {
    local name=$1
    local status=$2
    local message=$3
    RESULTS["$name"]="$status:$message"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ "$status" = "pass" ]; then
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    elif [ "$status" = "fail" ]; then
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        FAILURES+=("{\"check\": \"$name\", \"message\": \"$message\"}")
    elif [ "$status" = "warn" ]; then
        WARNINGS=$((WARNINGS + 1))
        WARNINGS_LIST+=("{\"check\": \"$name\", \"message\": \"$message\"}")
    fi
}

# Check if kubectl is available
if ! command -v kubectl &>/dev/null; then
    log "${RED}Error: kubectl not found${NC}"
    exit 2
fi

# Set KUBECONFIG if not set
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

# Verify cluster is reachable
if ! kubectl cluster-info &>/dev/null; then
    log "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
    exit 2
fi

log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log "${BLUE}🔍 Kubani Cluster Validation (Mode: ${MODE})${NC}"
log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log ""

# ============================================================================
# Section 1: Core Kubernetes Components
# ============================================================================
log "${CYAN}📦 Core Kubernetes Components${NC}"
log ""

# Check control plane components with specific labels
declare -A CORE_COMPONENTS=(
    ["coredns"]="k8s-app=kube-dns"
    ["metrics-server"]="k8s-app=metrics-server"
    ["local-path-provisioner"]="app=local-path-provisioner"
)

for component in "${!CORE_COMPONENTS[@]}"; do
    label="${CORE_COMPONENTS[$component]}"
    log -n "  $component: "
    pods=$(kubectl get pods -n kube-system -l "$label" --no-headers 2>/dev/null || echo "")
    if [ -n "$pods" ] && echo "$pods" | grep -q "Running"; then
        log "${GREEN}✓ Running${NC}"
        record_result "core-$component" "pass" "Running"
    else
        log "${RED}✗ Not running${NC}"
        record_result "core-$component" "fail" "Not running or not found"
    fi
done

# Check Traefik
log -n "  traefik: "
traefik_pods=$(kubectl get pods -n kube-system -l "app.kubernetes.io/name=traefik" --no-headers 2>/dev/null)
if echo "$traefik_pods" | grep -q "Running"; then
    # Get Traefik LoadBalancer IP
    traefik_ip=$(kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    log "${GREEN}✓ Running (LB IP: ${traefik_ip:-unknown})${NC}"
    record_result "core-traefik" "pass" "Running with LB IP: $traefik_ip"
else
    log "${RED}✗ Not running${NC}"
    record_result "core-traefik" "fail" "Not running"
fi

log ""

# ============================================================================
# Section 2: Flux CD GitOps
# ============================================================================
log "${CYAN}🔄 Flux CD GitOps${NC}"
log ""

for component in source-controller kustomize-controller helm-controller notification-controller; do
    log -n "  $component: "
    status=$(kubectl get pods -n flux-system -l "app=$component" -o jsonpath='{.items[0].status.phase}' 2>/dev/null)
    if [ "$status" = "Running" ]; then
        log "${GREEN}✓ Running${NC}"
        record_result "flux-$component" "pass" "Running"
    else
        log "${RED}✗ $status${NC}"
        record_result "flux-$component" "fail" "Status: $status"
    fi
done

# Check Kustomizations
log -n "  kustomizations: "
failed_ks=$(kubectl get kustomizations -A -o json 2>/dev/null | jq -r '.items[] | select(.status.conditions[] | select(.type=="Ready" and .status!="True")) | .metadata.name' 2>/dev/null | wc -l)
total_ks=$(kubectl get kustomizations -A --no-headers 2>/dev/null | wc -l)
if [ "$failed_ks" -eq 0 ] && [ "$total_ks" -gt 0 ]; then
    log "${GREEN}✓ All $total_ks ready${NC}"
    record_result "flux-kustomizations" "pass" "All $total_ks kustomizations ready"
elif [ "$failed_ks" -gt 0 ]; then
    log "${YELLOW}⚠ $failed_ks of $total_ks not ready${NC}"
    record_result "flux-kustomizations" "warn" "$failed_ks of $total_ks not ready"
else
    log "${RED}✗ No kustomizations found${NC}"
    record_result "flux-kustomizations" "fail" "No kustomizations found"
fi

# Check HelmReleases
log -n "  helmreleases: "
failed_hr=$(kubectl get helmreleases -A -o json 2>/dev/null | jq -r '.items[] | select(.status.conditions[] | select(.type=="Ready" and .status!="True")) | .metadata.name' 2>/dev/null | wc -l)
total_hr=$(kubectl get helmreleases -A --no-headers 2>/dev/null | wc -l)
if [ "$failed_hr" -eq 0 ] && [ "$total_hr" -gt 0 ]; then
    log "${GREEN}✓ All $total_hr ready${NC}"
    record_result "flux-helmreleases" "pass" "All $total_hr helmreleases ready"
elif [ "$failed_hr" -gt 0 ]; then
    log "${YELLOW}⚠ $failed_hr of $total_hr not ready${NC}"
    record_result "flux-helmreleases" "warn" "$failed_hr of $total_hr not ready"
else
    log "${RED}✗ No helmreleases found${NC}"
    record_result "flux-helmreleases" "fail" "No helmreleases found"
fi

log ""

# ============================================================================
# Section 3: Infrastructure Services
# ============================================================================
log "${CYAN}🏗️  Infrastructure Services${NC}"
log ""

# Services are declared as "tier:namespace:selector". The tier decides what an
# absent workload means, which is the whole point of this table:
#
#   required — the service is always-on; no pods is a failure
#   optional — the service is disabled by default (see the Service Tiers table
#              in docs/infrastructure/cluster/cluster-stability.md); no pods is
#              a legitimate state and reports as "not deployed"
#
# Both service sections run through check_service so a given state cannot mean
# "pass" in one section and "fail" in another.
check_service() {
    local prefix=$1 service=$2 tier=$3 namespace=$4 selector=$5
    local running_pods total_pods

    log -n "  $service: "
    running_pods=$(kubectl get pods -n "$namespace" -l "$selector" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    total_pods=$(kubectl get pods -n "$namespace" -l "$selector" --no-headers 2>/dev/null | wc -l)

    if [ "$running_pods" -eq "$total_pods" ] && [ "$total_pods" -gt 0 ]; then
        log "${GREEN}✓ $running_pods/$total_pods running${NC}"
        record_result "$prefix-$service" "pass" "$running_pods/$total_pods pods running"
    elif [ "$running_pods" -gt 0 ]; then
        log "${YELLOW}⚠ $running_pods/$total_pods running${NC}"
        record_result "$prefix-$service" "warn" "$running_pods/$total_pods pods running"
    elif [ "$total_pods" -eq 0 ] && [ "$tier" = "optional" ]; then
        log "${YELLOW}○ Not deployed (optional)${NC}"
        record_result "$prefix-$service" "pass" "Not deployed (optional tier)"
    else
        log "${RED}✗ No running pods${NC}"
        record_result "$prefix-$service" "fail" "No running pods"
    fi
}

declare -A INFRA_SERVICES=(
    ["cert-manager"]="required:cert-manager:app.kubernetes.io/name=cert-manager"
    ["external-dns"]="required:external-dns:app.kubernetes.io/name=external-dns"
    ["gpu-operator"]="required:gpu-operator:app=gpu-operator"
    ["prometheus"]="optional:monitoring:app.kubernetes.io/name=prometheus"
    ["grafana"]="optional:monitoring:app.kubernetes.io/name=grafana"
    ["loki"]="optional:monitoring:app.kubernetes.io/name=loki"
    ["promtail"]="optional:monitoring:app.kubernetes.io/name=promtail"
)

for service in "${!INFRA_SERVICES[@]}"; do
    IFS=':' read -r tier namespace selector <<< "${INFRA_SERVICES[$service]}"
    check_service "infra" "$service" "$tier" "$namespace" "$selector"
done

log ""

# ============================================================================
# Section 4: Application Services
# ============================================================================
log "${CYAN}🚀 Application Services${NC}"
log ""

declare -A APP_SERVICES=(
    ["postgresql"]="required:database:app.kubernetes.io/name=postgresql"
    ["redis"]="required:cache:app.kubernetes.io/name=redis"
    ["authentik"]="required:auth:app.kubernetes.io/name=authentik"
    ["temporal"]="required:temporal:app.kubernetes.io/component=frontend"
    ["vllm"]="required:vllm:app=vllm"
    ["falkordb"]="required:database:app.kubernetes.io/name=falkordb"
    ["qdrant"]="required:database:app.kubernetes.io/name=qdrant"
    ["registry"]="required:registry:app.kubernetes.io/name=registry"
)

for service in "${!APP_SERVICES[@]}"; do
    IFS=':' read -r tier namespace selector <<< "${APP_SERVICES[$service]}"
    check_service "app" "$service" "$tier" "$namespace" "$selector"
done

log ""

# ============================================================================
# Section 5: DNS Resolution (skip in quick mode)
# ============================================================================
if [ "$MODE" != "quick" ]; then
    log "${CYAN}🌐 DNS Resolution${NC}"
    log ""

    # Only hosts with a live Ingress belong here. external-dns runs
    # --policy=sync, so a retired service's record is reaped and the lookup
    # SHOULD fail — listing it would report the system working as a failure.
    DNS_HOSTS=(
        "grafana.almckay.io"
        "auth.almckay.io"
        "prometheus.almckay.io"
        "llm.almckay.io"
        "temporal.almckay.io"
        "falkordb.almckay.io"
        "qdrant.almckay.io"
        "postgres.almckay.io"
        "redis.almckay.io"
    )

    # Get all valid Traefik LoadBalancer IPs (from all nodes)
    traefik_ips=$(kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[*].ip}' 2>/dev/null | tr ' ' '\n')

    for host in "${DNS_HOSTS[@]}"; do
        log -n "  $host: "
        resolved_ip=$(nslookup "$host" 2>/dev/null | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | head -1)

        if [ -n "$resolved_ip" ]; then
            # Check if resolved IP matches any of the valid Traefik IPs (handles round-robin DNS)
            if echo "$traefik_ips" | grep -q "^${resolved_ip}$"; then
                log "${GREEN}✓ $resolved_ip (valid Traefik IP)${NC}"
                record_result "dns-$host" "pass" "Resolves to valid Traefik IP"
            else
                log "${YELLOW}⚠ $resolved_ip (not a Traefik IP)${NC}"
                record_result "dns-$host" "warn" "Resolves to $resolved_ip which is not a Traefik LoadBalancer IP"
            fi
        else
            log "${RED}✗ DNS lookup failed${NC}"
            record_result "dns-$host" "fail" "DNS lookup failed"
        fi
    done

    log ""
fi

# ============================================================================
# Section 6: HTTPS Connectivity (skip in quick mode)
# ============================================================================
if [ "$MODE" != "quick" ]; then
    log "${CYAN}🔒 HTTPS Connectivity${NC}"
    log ""

    # Always-on endpoints. A bad response here is a genuine failure.
    HTTPS_ENDPOINTS=(
        "https://auth.almckay.io"
        "https://temporal.almckay.io"
        "https://falkordb.almckay.io"
        "https://qdrant.almckay.io"
    )

    # Endpoints backed by optional-tier workloads, as "url|namespace|selector".
    # These are probed only when the backend has running pods: while the
    # monitoring stack is scaled to zero the Ingress answers 503 with no
    # backend, which is expected and must not fail the run. Scale it back up
    # and these start being validated again automatically — no edit required.
    OPTIONAL_HTTPS_ENDPOINTS=(
        "https://grafana.almckay.io|monitoring|app.kubernetes.io/name=grafana"
        "https://prometheus.almckay.io|monitoring|app.kubernetes.io/name=prometheus"
    )

    for entry in "${OPTIONAL_HTTPS_ENDPOINTS[@]}"; do
        IFS='|' read -r url namespace selector <<< "$entry"
        host="${url#https://}"
        backend_pods=$(kubectl get pods -n "$namespace" -l "$selector" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
        if [ "$backend_pods" -gt 0 ]; then
            HTTPS_ENDPOINTS+=("$url")
        else
            log "  $host: ${YELLOW}○ Skipped (optional backend scaled down)${NC}"
            record_result "https-$host" "pass" "Skipped: optional backend scaled down"
        fi
    done

    for url in "${HTTPS_ENDPOINTS[@]}"; do
        host=$(echo "$url" | sed 's|https://||')
        log -n "  $host: "

        # curl already writes 000 via -w when the connection fails; the old
        # `|| echo 000` appended a second one and reported "HTTP 000000".
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "$url" 2>/dev/null) || true
        http_code="${http_code:-000}"

        if [ "$http_code" = "200" ] || [ "$http_code" = "302" ] || [ "$http_code" = "301" ] || [ "$http_code" = "303" ]; then
            log "${GREEN}✓ HTTP $http_code${NC}"
            record_result "https-$host" "pass" "HTTP $http_code"
        elif [ "$http_code" = "401" ] || [ "$http_code" = "403" ]; then
            log "${GREEN}✓ HTTP $http_code (auth required)${NC}"
            record_result "https-$host" "pass" "HTTP $http_code (authentication required)"
        elif [ "$http_code" = "000" ]; then
            log "${RED}✗ Connection failed${NC}"
            record_result "https-$host" "fail" "Connection failed"
        else
            log "${YELLOW}⚠ HTTP $http_code${NC}"
            record_result "https-$host" "warn" "HTTP $http_code"
        fi
    done

    log ""
fi

# ============================================================================
# Section 7: TCP Services (skip in quick mode)
# ============================================================================
if [ "$MODE" != "quick" ]; then
    log "${CYAN}🔌 TCP Services${NC}"
    log ""

    # One entry per Traefik TCP entry point (see infrastructure/traefik/README.md)
    declare -A TCP_SERVICES=(
        ["postgres.almckay.io:5432"]="PostgreSQL"
        ["redis.almckay.io:6379"]="Redis"
        ["falkordb.almckay.io:6380"]="FalkorDB"
        ["temporal.almckay.io:7233"]="Temporal"
    )

    for endpoint in "${!TCP_SERVICES[@]}"; do
        host=$(echo "$endpoint" | cut -d: -f1)
        port=$(echo "$endpoint" | cut -d: -f2)
        name="${TCP_SERVICES[$endpoint]}"

        log -n "  $name ($endpoint): "

        if nc -z -w 3 "$host" "$port" 2>/dev/null; then
            log "${GREEN}✓ Port open${NC}"
            record_result "tcp-$name" "pass" "Port $port accessible"
        else
            log "${RED}✗ Connection failed${NC}"
            record_result "tcp-$name" "fail" "Cannot connect to port $port"
        fi
    done

    log ""
fi

# ============================================================================
# Section 8: Certificates (only in full mode)
# ============================================================================
if [ "$MODE" = "full" ]; then
    log "${CYAN}📜 TLS Certificates${NC}"
    log ""

    certs=$(kubectl get certificates -A -o json 2>/dev/null)
    cert_count=$(echo "$certs" | jq -r '.items | length')

    if [ "$cert_count" -gt 0 ]; then
        echo "$certs" | jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name) \(.status.conditions[] | select(.type=="Ready") | .status)"' 2>/dev/null | while read -r name status; do
            log -n "  $name: "
            if [ "$status" = "True" ]; then
                log "${GREEN}✓ Valid${NC}"
            else
                log "${RED}✗ Not ready${NC}"
            fi
        done

        ready_certs=$(echo "$certs" | jq -r '[.items[] | select(.status.conditions[] | select(.type=="Ready" and .status=="True"))] | length')
        record_result "certs-status" "pass" "$ready_certs of $cert_count certificates ready"
    else
        log "  ${YELLOW}No certificates found${NC}"
        record_result "certs-status" "warn" "No certificates found"
    fi

    log ""
fi

# ============================================================================
# Section 9: Node Health (only in full mode)
# ============================================================================
if [ "$MODE" = "full" ]; then
    log "${CYAN}🖥️  Node Health${NC}"
    log ""

    nodes=$(kubectl get nodes -o json 2>/dev/null)

    echo "$nodes" | jq -r '.items[] | "\(.metadata.name) \(.status.conditions[] | select(.type=="Ready") | .status)"' 2>/dev/null | while read -r name status; do
        log -n "  $name: "
        if [ "$status" = "True" ]; then
            log "${GREEN}✓ Ready${NC}"
        else
            log "${RED}✗ Not Ready${NC}"
        fi
    done

    total_nodes=$(echo "$nodes" | jq -r '.items | length')
    ready_nodes=$(echo "$nodes" | jq -r '[.items[] | select(.status.conditions[] | select(.type=="Ready" and .status=="True"))] | length')

    if [ "$ready_nodes" -eq "$total_nodes" ]; then
        record_result "nodes-health" "pass" "$ready_nodes of $total_nodes nodes ready"
    else
        record_result "nodes-health" "fail" "$ready_nodes of $total_nodes nodes ready"
    fi

    log ""
fi

# ============================================================================
# Summary
# ============================================================================
log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log "${BLUE}📊 Summary${NC}"
log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
log ""
log "  Total checks: $TOTAL_CHECKS"
log "  ${GREEN}Passed: $PASSED_CHECKS${NC}"
log "  ${YELLOW}Warnings: $WARNINGS${NC}"
log "  ${RED}Failed: $FAILED_CHECKS${NC}"
log ""

# Calculate overall status
if [ "$FAILED_CHECKS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    log "${GREEN}✅ All checks passed! Cluster is healthy.${NC}"
    OVERALL_STATUS="healthy"
    EXIT_CODE=0
elif [ "$FAILED_CHECKS" -eq 0 ]; then
    log "${YELLOW}⚠️  Cluster operational with warnings. Review recommended.${NC}"
    OVERALL_STATUS="warning"
    EXIT_CODE=0
else
    log "${RED}❌ Cluster has issues that need attention.${NC}"
    OVERALL_STATUS="unhealthy"
    EXIT_CODE=1

    log ""
    log "${RED}Failed checks:${NC}"
    for key in "${!RESULTS[@]}"; do
        IFS=':' read -r status message <<< "${RESULTS[$key]}"
        if [ "$status" = "fail" ]; then
            log "  - $key: $message"
        fi
    done
fi

log ""

# JSON output
if [ "$JSON_OUTPUT" = true ]; then
    failures_json=$(IFS=','; echo "[${FAILURES[*]}]")
    warnings_json=$(IFS=','; echo "[${WARNINGS_LIST[*]}]")

    cat <<EOF
{
  "status": "$OVERALL_STATUS",
  "timestamp": "$(date -Iseconds)",
  "mode": "$MODE",
  "summary": {
    "total": $TOTAL_CHECKS,
    "passed": $PASSED_CHECKS,
    "warnings": $WARNINGS,
    "failed": $FAILED_CHECKS
  },
  "failures": $failures_json,
  "warnings": $warnings_json
}
EOF
fi

exit $EXIT_CODE
