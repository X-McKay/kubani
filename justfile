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
    ansible-inventory -i {{inventory_file}} --list >/dev/null
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

validate-gitops-build:
    for dir in \
        infrastructure/gitops/infrastructure \
        infrastructure/gitops/apps/databases \
        infrastructure/gitops/apps \
        infrastructure/gitops/flux-system; do \
        echo "Validating $dir"; \
        kubectl kustomize "$dir" >/dev/null; \
    done

validate-flux:
    ./infrastructure/scripts/validate_kustomizations.sh

validate-cluster:
    ./infrastructure/scripts/validate_cluster.sh

live-service-probes:
    ./infrastructure/scripts/live_service_probes.py

live-service-probes-internal:
    ./infrastructure/scripts/live_service_probes.py --internal-only

post-reconcile-validate: validate-flux live-service-probes

validate-local: inventory secrets-check validate-gitops-build

validate: validate-local validate-cluster

lint:
    uv run ansible-lint infrastructure/ansible

check:
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
