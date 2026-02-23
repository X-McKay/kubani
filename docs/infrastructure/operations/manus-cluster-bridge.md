# Manus Cluster Bridge

**Author:** Manus AI
**Date:** 2026-02-23

This document describes the architecture, setup procedure, and usage model for the secure bridge that allows Manus to read and modify the state of the private Kubernetes cluster without exposing any cluster endpoints to the public internet.

## Architecture

The bridge is built on three components that work together to form a secure, asynchronous communication channel.

The first component is a **self-hosted GitHub Actions runner** deployed as a pod inside the Kubernetes cluster. This pod is the only piece of infrastructure with simultaneous access to both the Kubernetes API server (via a scoped service account) and the GitHub Actions service (via an outbound HTTPS connection). Because the connection is always outbound from the cluster, no firewall rules or network configuration changes are required.

The second component is a pair of **GitHub Actions workflows** — `command.yml` for state-changing operations and `get-state.yml` for read-only queries — stored in this repository. These workflows are triggered via `workflow_dispatch` events, which Manus fires using the `gh` CLI. Each workflow accepts a `kubectl` command string and a unique `job_id` as inputs.

The third component is **GitHub Actions Artifacts**, which serve as the return channel. After the runner executes the command, it writes the full output (stdout, stderr, exit code, and metadata) to a `result.txt` file and uploads it as a named artifact. Manus then polls for the workflow to complete and downloads the artifact to retrieve the result.

```
Manus (Public Internet)
    |
    | 1. gh workflow run (HTTPS to github.com)
    v
GitHub Actions
    |
    | 2. Job dispatched to self-hosted runner
    v
Runner Pod (inside cluster, outbound connection only)
    |
    | 3. kubectl <command>
    v
Kubernetes API Server (private network)
    |
    | 4. Result
    v
Runner Pod
    |
    | 5. Upload artifact (HTTPS to github.com)
    v
GitHub Actions Artifacts
    |
    | 6. gh run download (HTTPS to github.com)
    v
Manus
```

## Setup

### Step 1: Create a GitHub App

A GitHub App provides more secure and auditable authentication than a Personal Access Token. Navigate to your GitHub organization's settings, then **Developer settings > GitHub Apps**, and create a new app with the following configuration.

| Setting | Value |
|---|---|
| GitHub App name | `manus-runner-kubani` |
| Homepage URL | `https://github.com/X-McKay/kubani` |
| Webhook | Disabled (uncheck "Active") |
| Repository permissions — Actions | Read-only |
| Repository permissions — Contents | Read & write |
| Repository permissions — Metadata | Read-only |

After creating the app, generate a private key from the app's settings page and download the `.pem` file. Then install the app on the `X-McKay/kubani` repository. Note the **App ID** (shown on the app's main settings page) and the **Installation ID** (visible in the URL when viewing the installation: `.../installations/<INSTALLATION_ID>`).

### Step 2: Create the Kubernetes Secret

The GitHub App credentials must be stored as a Kubernetes secret in the `actions-runner-system` namespace **before** Flux deploys the Helm chart, as the chart references this secret by name.

```bash
# Create the namespace first if it does not yet exist
kubectl create namespace actions-runner-system

# Create the secret from the downloaded .pem file
kubectl create secret generic arc-github-app \
  --namespace actions-runner-system \
  --from-literal=github_app_id=<YOUR_APP_ID> \
  --from-literal=github_app_installation_id=<YOUR_INSTALLATION_ID> \
  --from-file=github_app_private_key=<PATH_TO_YOUR_PEM_FILE>
```

This secret is intentionally not managed by Flux or SOPS to keep the private key out of the Git repository entirely.

### Step 3: Deploy via Flux

Once the secret is in place, push the changes in this branch to `main`. Flux will detect the new `github-runner/` entry in `infrastructure/gitops/apps/kustomization.yaml` and deploy the following resources in order:

1. The `actions-runner-system` namespace.
2. The `HelmRepository` source pointing to the ARC chart registry.
3. The `actions-runner-controller` Helm release.
4. The `manus-runner` ServiceAccount, ClusterRole, and ClusterRoleBinding.
5. The `RunnerDeployment` that creates the runner pod.

Verify the runner is online by checking the repository's **Settings > Actions > Runners** page. A runner named `manus-runner` with the `manus-runner` label should appear as **Idle**.

### Step 4: Verify the Connection

Run a simple read-only command to confirm the end-to-end flow is working.

```bash
# Generate a unique job ID
JOB_ID="manus-verify-$(date +%s)"

# Trigger the workflow
gh workflow run get-state.yml \
  --repo X-McKay/kubani \
  --field command="get nodes" \
  --field job_id="${JOB_ID}"

# Wait a moment, then find the run ID
sleep 5
RUN_ID=$(gh run list --repo X-McKay/kubani --workflow get-state.yml --limit 1 --json databaseId --jq '.[0].databaseId')

# Wait for the run to complete
gh run watch "${RUN_ID}" --repo X-McKay/kubani

# Download and display the result
gh run download "${RUN_ID}" --repo X-McKay/kubani --name "${JOB_ID}" --dir ./result
cat ./result/result.txt
```

## Usage

Manus interacts with the cluster by triggering the two workflows via the `gh` CLI. The general pattern is always the same: trigger, wait, retrieve.

### Reading Cluster State

Use `get-state.yml` for any read-only `kubectl` command. The `command` input is passed directly to `kubectl`, so any valid `kubectl` arguments are supported.

```bash
# Get all pods across all namespaces
gh workflow run get-state.yml \
  --repo X-McKay/kubani \
  --field command="get pods --all-namespaces -o wide" \
  --field job_id="manus-pods-$(date +%s)"

# Describe a specific deployment
gh workflow run get-state.yml \
  --repo X-McKay/kubani \
  --field command="describe deployment my-app -n default" \
  --field job_id="manus-describe-$(date +%s)"

# Get recent events for a namespace
gh workflow run get-state.yml \
  --repo X-McKay/kubani \
  --field command="get events -n nexus --sort-by='.lastTimestamp'" \
  --field job_id="manus-events-$(date +%s)"
```

### Making Changes

Use `command.yml` for state-changing operations. The runner's RBAC permissions govern what is and is not permitted.

```bash
# Restart a deployment
gh workflow run command.yml \
  --repo X-McKay/kubani \
  --field command="rollout restart deployment/my-app -n default" \
  --field job_id="manus-restart-$(date +%s)"

# Scale a deployment
gh workflow run command.yml \
  --repo X-McKay/kubani \
  --field command="scale deployment/my-app --replicas=3 -n default" \
  --field job_id="manus-scale-$(date +%s)"
```

## Security Model

The security of this bridge rests on three principles.

**No inbound connections.** The runner pod connects outbound to `github.com` to poll for jobs. The cluster's network perimeter is unchanged. No ports are opened, no firewall rules are modified, and no Tailscale configuration is altered.

**Least-privilege RBAC.** The `manus-runner` service account is bound to a `ClusterRole` that grants the minimum permissions required. Read access is broad (pods, deployments, services, etc.), but write access is narrowly scoped to specific verbs on specific resource types. The RBAC manifest in `infrastructure/gitops/apps/github-runner/rbac.yaml` is the authoritative definition of what Manus is allowed to do.

**Complete audit trail.** Every action Manus takes is recorded as a GitHub Actions workflow run, providing an immutable, timestamped log of every command executed against the cluster. This log is visible in the repository's **Actions** tab.

## RBAC Permissions Reference

The following table summarises the permissions granted to the `manus-runner` service account.

| API Group | Resources | Allowed Verbs |
|---|---|---|
| `""` (core) | pods, pods/log, pods/status, services, endpoints, namespaces, nodes, configmaps, events, PVCs, PVs | `get`, `list`, `watch` |
| `""` (core) | pods | `delete` |
| `apps` | deployments, replicasets, statefulsets, daemonsets | `get`, `list`, `watch` |
| `apps` | deployments, statefulsets | `patch`, `update` |
| `batch` | jobs, cronjobs | `get`, `list`, `watch`, `create`, `delete` |
| `networking.k8s.io` | ingresses | `get`, `list`, `watch` |
| `helm.toolkit.fluxcd.io` | helmreleases | `get`, `list`, `watch` |
| `kustomize.toolkit.fluxcd.io` | kustomizations | `get`, `list`, `watch` |

To grant additional permissions, edit `infrastructure/gitops/apps/github-runner/rbac.yaml` and commit the change. Flux will apply the update automatically.
