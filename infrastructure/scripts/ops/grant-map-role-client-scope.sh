#!/usr/bin/env bash
# Let the registry controller map agent-role-* realm roles into an agent client's
# scope (zetra platform/controller idp.py _sync_agent_roles, spec 7.3).
#
# Why: the agents realm runs Keycloak's fine-grained admin permissions v2
# (adminPermissionsEnabled: true, feature admin-fine-grained-authz:v2). Under v2,
# POST /clients/{id}/scope-mappings/realm needs either realm-management
# `manage-realm` or a v2 permission `map-role-client-scope` on the role
# (RolePermissionsV2.canMapClientScope). The controller holds manage-clients,
# manage-users and view-realm; those do not grant this operation for realm roles.
# Historical missing scope mappings returned 403 (qualification finding 14).
#
# This grants the narrow v2 permission rather than manage-realm: one client policy
# (registry-controller) and one scope permission (resource type Roles, scope
# map-role-client-scope, all realm roles). Scope mappings only let a token carry a
# role the service-account user already holds; the user role mapping itself stays
# under manage-users and v2 canMapRole, which refuses admin roles.
#
# Verified 2026-11-06 16:57 UTC against Keycloak 26.8.1: evaluating the
# registry-controller service-account user WITH clientId=registry-controller's
# internal UUID returns PERMIT. The controller's own credentials returned 204
# for an idempotent POST of an existing role to conformance-b's realm scope;
# the mapping set was identical before/after. Evaluating only the user defaults
# to the admin-permissions client and returns DENY for this client policy.
# This does not explain the historical 403, but proves the current grant works.
#
# Operator-run on rig0 (the permission-grant guard may require a real terminal):
#   bash infrastructure/scripts/ops/grant-map-role-client-scope.sh
# Secrets remain in Keycloak's existing environment and are never printed or
# copied to this script. Idempotent: skips objects that already exist; it does
# not overwrite existing policies. Evaluate existing objects if they differ.
# No manage-realm grant is needed. References and verification evidence:
# docs/infrastructure/configuration/agent-runtime-platform-phase-b-qualification.md
set -euo pipefail
export KUBECONFIG=/home/al/.kube/config
KC=$(kubectl get pod -n auth -l app.kubernetes.io/name=keycloak -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n auth "$KC" -- sh -c '
set -e
K=/opt/keycloak/bin/kcadm.sh
$K config credentials --server http://localhost:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null
id() { grep -o "[0-9a-f-]\{36\}" | head -1; }
AP=$($K get clients -r agents -q clientId=admin-permissions --fields id | id)
RC=$($K get clients -r agents -q clientId=registry-controller --fields id | id)
echo "admin-permissions=$AP registry-controller=$RC"
PID=$($K get clients/$AP/authz/resource-server/policy -r agents -q name=registry-controller --fields id | id || true)
if [ -z "$PID" ]; then
  $K create clients/$AP/authz/resource-server/policy/client -r agents \
    -b "{\"name\":\"registry-controller\",\"description\":\"The registry controller client (spec 7.5)\",\"clients\":[\"$RC\"],\"logic\":\"POSITIVE\"}"
  PID=$($K get clients/$AP/authz/resource-server/policy -r agents -q name=registry-controller --fields id | id)
fi
echo "policy registry-controller=$PID"
PERM=$($K get clients/$AP/authz/resource-server/permission -r agents -q name=registry-controller-map-role-client-scope --fields id | id || true)
if [ -z "$PERM" ]; then
  $K create clients/$AP/authz/resource-server/permission/scope -r agents \
    -b "{\"name\":\"registry-controller-map-role-client-scope\",\"description\":\"Spec 7.3: the controller puts an agent-role-* realm role into an agent client scope (fullScopeAllowed false)\",\"resourceType\":\"Roles\",\"scopes\":[\"map-role-client-scope\"],\"policies\":[\"$PID\"],\"decisionStrategy\":\"UNANIMOUS\"}"
fi
echo "== permissions"
$K get clients/$AP/authz/resource-server/permission -r agents --fields name,resourceType,scopes | tr -d " \n"; echo
'
echo "Check Agent readiness and evaluate with both the service-account user and controller client identity."
