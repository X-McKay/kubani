set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

inventory_file := "infrastructure/ansible/inventory/hosts.yml"
ansible_dir := "infrastructure/ansible"

default:
    @just --list --unsorted

setup:
    mise install
    uv sync --group dev
    just ansible-deps
    uv run pre-commit install

ansible-deps:
    mkdir -p .ansible/collections
    uv run ansible-galaxy collection install -r infrastructure/ansible/requirements.yml -p .ansible/collections

inventory:
    uv run ansible-inventory -i {{inventory_file}} --list >/dev/null
    @echo "Inventory is valid"

ansible-ping:
    uv run ansible all -i {{inventory_file}} -m ping

preflight:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/preflight_checks.yml

site:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/site.yml

provision:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml

upgrade-k3s:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml -e k3s_allow_upgrade=true

bootstrap-flux:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/bootstrap_flux.yml

repair-flux-bootstrap:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/bootstrap_flux.yml -e gitops_allow_bootstrap_repair=true

upgrade-flux-cli:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/bootstrap_flux.yml -e gitops_bootstrap_enabled=false -e flux_cli_allow_upgrade=true

upgrade-flux-controllers:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/bootstrap_flux.yml -e gitops_allow_flux_upgrade=true

provision-host host:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml --limit {{host}}

add-node host:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/add_node.yml --limit {{host}}

bootstrap-node host:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/bootstrap_node.yml --limit {{host}}

ssh-keys:
    ./infrastructure/scripts/setup_ssh_keys.sh

known-hosts-refresh:
    bash ./infrastructure/scripts/refresh_known_hosts.sh

sudo-bootstrap:
    ./infrastructure/scripts/setup_passwordless_sudo.sh

connectivity:
    ./infrastructure/scripts/check_connectivity.sh

secrets-check:
    find infrastructure -name '*.enc.yaml' -print0 | xargs -0 ./infrastructure/scripts/pre-commit/check-sops-encryption.sh
    # Whole-tree scan, not just changed files: a plaintext Secret that is
    # already committed is invisible to the pre-commit hooks forever.
    uv run python infrastructure/scripts/pre-commit/check-plaintext-secrets.py --all

# Report drift between what the repo claims and what exists. Advisory.
drift:
    uv run python infrastructure/scripts/check_drift.py

drift-offline:
    uv run python infrastructure/scripts/check_drift.py --no-cluster

# Assert the local clone is actually protected. `just setup` installs the git
# hooks, but nothing used to verify they were installed — and on at least one
# clone they were not, so every secret scan depended on someone typing
# `just check` by hand.
hooks-check:
    #!/usr/bin/env bash
    set -euo pipefail
    # Git hooks are per-clone developer state. CI checks out fresh every run, so
    # there is nothing to assert and nothing a hook would protect -- CI runs the
    # same scans directly. Asserting here would fail every scheduled audit for a
    # reason unrelated to system health.
    if [ -n "${CI:-}" ]; then
        echo "  git hooks: skipped (CI runs the scans directly)"
        exit 0
    fi
    missing=0
    for hook in pre-commit pre-push; do
        hook_path="$(git rev-parse --git-path "hooks/$hook")"
        if [ -f "$hook_path" ] && grep -q pre-commit "$hook_path" 2>/dev/null; then
            echo "  $hook hook: installed"
        else
            echo "  $hook hook: MISSING"
            missing=1
        fi
    done
    if [ "$missing" -ne 0 ]; then
        echo ""
        echo "Run 'uv run pre-commit install' (or 'just setup') to install them."
        exit 1
    fi

# Everything that can run without touching the cluster. Named pre-push rather
# than preflight because `preflight` is already the Ansible pre-provision play.
pre-push-check: hooks-check validate-local drift-offline

validate-gitops-build:
    for dir in \
        infrastructure/gitops/infrastructure \
        infrastructure/gitops/apps/databases \
        infrastructure/gitops/apps/starbase-phase4a \
        infrastructure/gitops/apps \
        infrastructure/gitops/flux-system; do \
        echo "Validating $dir"; \
        kubectl kustomize "$dir" >/dev/null; \
    done

test-starbase-promotion:
    uv run python -m unittest tests.test_starbase_promotion tests.test_starbase_phase4a -v

starbase-promotion-generate evidence_source starbase_source:
    uv run python infrastructure/scripts/starbase_promotion.py generate \
        --evidence-source {{evidence_source}} \
        --starbase-source {{starbase_source}} \
        --input infrastructure/gitops/apps/starbase/promotion-input.json \
        --output infrastructure/gitops/apps/starbase/rendered.yaml \
        --lock infrastructure/gitops/apps/starbase/promotion-lock.json \
        --kubectl "$(command -v kubectl)"

starbase-promotion-verify evidence_source starbase_source:
    uv run python infrastructure/scripts/starbase_promotion.py verify \
        --evidence-source {{evidence_source}} \
        --starbase-source {{starbase_source}} \
        --input infrastructure/gitops/apps/starbase/promotion-input.json \
        --output infrastructure/gitops/apps/starbase/rendered.yaml \
        --lock infrastructure/gitops/apps/starbase/promotion-lock.json \
        --kubectl "$(command -v kubectl)"

validate-flux:
    ./infrastructure/scripts/validate_kustomizations.sh

validate-cluster:
    ./infrastructure/scripts/validate_cluster.sh

# Distinct from validate-cluster, which is kubectl-based and runs from
# anywhere. Host-local network validation: must run ON a node, since it
# reads that host's routes, UFW state and iptables chains.
validate-network:
    ./infrastructure/scripts/validate-cluster-network.sh

# NOT provision_cluster.yml: its prerequisites include_role is tagged `prerequisites`
# and include_role is dynamic, so --tags firewall never reaches firewall.yml; and its
# worker play asserts on k3s_node_token (tags: always), which only exists after the
# control-plane play, so any --limit <worker> run fails first. A full provisioning run
# could also restart K3s, and rig0 is the operator's workstation. ARGS is variadic so
# `just firewall-apply rig0 --check --diff` works.
# Apply only the firewall tasks, via a dedicated playbook.
firewall-apply host *ARGS:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/firewall.yml --limit {{host}} {{ARGS}}

# Dry-run provisioning across all nodes. Reports configuration drift and proves
# the provisioning path still works. Changes nothing.
# No --limit: the control-plane play publishes k3s_node_token via add_host, and
# limiting to a worker skips that play, so the worker-play assert fails.
provision-check:
    uv run ansible-playbook -i {{inventory_file}} {{ansible_dir}}/playbooks/provision_cluster.yml --check --diff

live-service-probes:
    ./infrastructure/scripts/live_service_probes.py

live-service-probes-internal:
    ./infrastructure/scripts/live_service_probes.py --internal-only

post-reconcile-validate: validate-flux live-service-probes

validate-local: inventory secrets-check validate-gitops-build test-starbase-promotion hooks-check

validate: validate-local validate-cluster

# Fail fast if kubectl is pointed at the wrong cluster, so the checks below
# cannot pass while asserting nothing about kubani.
cluster-identity:
    ./infrastructure/scripts/check-cluster-identity.sh

# Everything that asserts the running system matches what is declared.
# This is what the scheduled audit runs; keep it as the single entry point so
# the scheduler stays a dumb transport.
# provision-check is deliberately still excluded: its drift output needs to be
# stable and explainable across several manual runs before it is allowed to fail
# a scheduled job. Adding it later is a one-word change with no workflow edit.
audit: cluster-identity validate validate-network live-service-probes

lint:
    uv run ansible-lint infrastructure/ansible

check:
    @mapfile -d '' -t files < <( \
        { \
            git diff -z --name-only --diff-filter=ACMR HEAD; \
            git ls-files -z --others --exclude-standard; \
        } | sort -zu \
    ); \
    if (( ${#files[@]} == 0 )); then \
        uv run pre-commit run; \
    else \
        uv run pre-commit run --files "${files[@]}"; \
    fi

check-all:
    uv run pre-commit run --all-files

nodes:
    kubectl get nodes -o wide

pods:
    kubectl get pods -A

pods-ns namespace:
    kubectl get pods -n {{namespace}}

flux-status:
    flux get all -A

flux-reconcile-only target:
    flux reconcile kustomization {{target}} -n flux-system --with-source

flux-reconcile:
    just flux-reconcile-only infrastructure
    just flux-reconcile-only databases
    just flux-reconcile-only apps
    just post-reconcile-validate
