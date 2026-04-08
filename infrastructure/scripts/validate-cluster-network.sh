#!/usr/bin/env bash
# validate-cluster-network.sh
#
# Validates cluster network health after Tailscale or K3s events.
# Checks:
#   1. tailscale0 interface presence and IP
#   2. Pod CIDR routes for all nodes (10.42.x.0/24)
#   3. CoreDNS reachability
#   4. Cross-node pod connectivity
#
# Usage:
#   ./infrastructure/scripts/validate-cluster-network.sh
#   just validate-cluster
#
# Exit codes:
#   0 - all checks passed
#   1 - one or more checks failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

pass() { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $*"; }
section() { echo ""; echo "=== $* ==="; }

FAILURES=0

# ---------------------------------------------------------------------------
# 1. Tailscale interface check
# ---------------------------------------------------------------------------
section "Tailscale Interface"

if ip link show tailscale0 &>/dev/null; then
    TS_IP=$(ip -4 addr show tailscale0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
    if [[ -n "$TS_IP" ]]; then
        pass "tailscale0 is up with IP $TS_IP"
    else
        fail "tailscale0 exists but has no IPv4 address"
    fi
else
    fail "tailscale0 interface not found — Tailscale may not be running"
fi

# ---------------------------------------------------------------------------
# 2. Pod CIDR route check
# ---------------------------------------------------------------------------
section "Pod CIDR Routes (10.42.x.0/24)"

# Collect all routes in the 10.42.0.0/16 range
mapfile -t ROUTES < <(ip route show | grep -E '^10\.42\.' || true)

if [[ ${#ROUTES[@]} -eq 0 ]]; then
    fail "No pod CIDR routes found — Flannel routes are missing entirely"
    echo ""
    echo "  To restore routes, restart K3s:"
    echo "    sudo systemctl restart k3s        # control plane"
    echo "    sudo systemctl restart k3s-agent  # worker nodes"
else
    pass "Found ${#ROUTES[@]} pod CIDR route(s):"
    for route in "${ROUTES[@]}"; do
        echo "      $route"
    done

    # If kubectl is available, cross-check against expected node pod CIDRs
    if command -v kubectl &>/dev/null && kubectl get nodes &>/dev/null 2>&1; then
        section "Cross-checking routes against node pod CIDRs"
        MISSING_ROUTES=()
        while IFS= read -r line; do
            node=$(echo "$line" | awk '{print $1}')
            cidr=$(echo "$line" | awk '{print $2}')
            [[ -z "$cidr" || "$cidr" == "<none>" ]] && continue
            if ip route show | grep -q "^${cidr}"; then
                pass "Route to $cidr ($node) present"
            else
                fail "Route to $cidr ($node) is MISSING"
                MISSING_ROUTES+=("$cidr ($node)")
            fi
        done < <(kubectl get nodes -o custom-columns='NAME:.metadata.name,PODCIDR:.spec.podCIDR' --no-headers 2>/dev/null)

        if [[ ${#MISSING_ROUTES[@]} -gt 0 ]]; then
            echo ""
            echo "  Missing routes:"
            for r in "${MISSING_ROUTES[@]}"; do
                echo "    - $r"
            done
            echo ""
            echo "  To restore, restart K3s on the affected node:"
            echo "    sudo systemctl restart k3s-agent  # worker"
            echo "    sudo systemctl restart k3s        # control plane"
        fi
    else
        warn "kubectl not available or cluster unreachable — skipping per-node CIDR cross-check"
    fi
fi

# ---------------------------------------------------------------------------
# 3. CoreDNS reachability
# ---------------------------------------------------------------------------
section "CoreDNS Reachability"

COREDNS_SVC_IP=""
if command -v kubectl &>/dev/null && kubectl get svc -n kube-system kube-dns &>/dev/null 2>&1; then
    COREDNS_SVC_IP=$(kubectl get svc -n kube-system kube-dns -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)
fi

if [[ -n "$COREDNS_SVC_IP" ]]; then
    # Test UDP port 53 reachability with a short timeout
    if timeout 3 bash -c "echo '' > /dev/udp/${COREDNS_SVC_IP}/53" 2>/dev/null; then
        pass "CoreDNS service IP $COREDNS_SVC_IP is reachable on UDP/53"
    else
        # Fall back to nslookup if available
        if command -v nslookup &>/dev/null; then
            if nslookup kubernetes.default.svc.cluster.local "$COREDNS_SVC_IP" &>/dev/null 2>&1; then
                pass "CoreDNS service IP $COREDNS_SVC_IP responds to DNS queries"
            else
                fail "CoreDNS service IP $COREDNS_SVC_IP is not responding to DNS queries"
            fi
        else
            warn "Cannot test CoreDNS UDP/53 directly (no nslookup); skipping DNS query test"
        fi
    fi
else
    warn "Could not determine CoreDNS service IP — kubectl unavailable or kube-dns service not found"
    # Try the well-known default CoreDNS IP for K3s clusters
    DEFAULT_DNS="10.43.0.10"
    if timeout 2 bash -c "echo '' > /dev/udp/${DEFAULT_DNS}/53" 2>/dev/null; then
        pass "Default CoreDNS IP $DEFAULT_DNS is reachable on UDP/53"
    else
        warn "Default CoreDNS IP $DEFAULT_DNS not reachable (may be expected if kubectl is unavailable)"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Cross-node pod connectivity
# ---------------------------------------------------------------------------
section "Cross-node Pod Connectivity"

if ! command -v kubectl &>/dev/null || ! kubectl get nodes &>/dev/null 2>&1; then
    warn "kubectl not available or cluster unreachable — skipping cross-node connectivity test"
else
    # Find a pod on a different node than the current host
    LOCAL_HOSTNAME=$(hostname)
    REMOTE_POD_IP=""
    REMOTE_NODE=""

    while IFS= read -r line; do
        pod_ip=$(echo "$line" | awk '{print $1}')
        node=$(echo "$line" | awk '{print $2}')
        [[ -z "$pod_ip" || "$pod_ip" == "<none>" ]] && continue
        [[ "$node" == "$LOCAL_HOSTNAME" ]] && continue
        REMOTE_POD_IP="$pod_ip"
        REMOTE_NODE="$node"
        break
    done < <(kubectl get pods -A -o custom-columns='IP:.status.podIP,NODE:.spec.nodeName' --no-headers 2>/dev/null | grep -v '<none>' || true)

    if [[ -n "$REMOTE_POD_IP" ]]; then
        if ping -c 2 -W 2 "$REMOTE_POD_IP" &>/dev/null 2>&1; then
            pass "Cross-node ping to pod $REMOTE_POD_IP on $REMOTE_NODE succeeded"
        else
            fail "Cross-node ping to pod $REMOTE_POD_IP on $REMOTE_NODE FAILED — pod network may be broken"
            echo ""
            echo "  This usually means Flannel routes are missing or the Tailscale tunnel is down."
            echo "  Run: ip route show | grep 10.42"
            echo "  Then restart K3s if routes are absent."
        fi
    else
        warn "No remote pods found to test cross-node connectivity (cluster may be empty or single-node)"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}✓ All network checks passed${NC}"
    echo "========================================"
    exit 0
else
    echo -e "${RED}✗ $FAILURES check(s) failed${NC}"
    echo "========================================"
    echo ""
    echo "See output above for details."
    echo "Common fix: sudo systemctl restart k3s-agent  (or k3s on control plane)"
    exit 1
fi
