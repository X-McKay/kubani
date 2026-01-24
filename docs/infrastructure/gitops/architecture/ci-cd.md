# CI/CD Plan for Agent Auto-Deployment

## Current State Analysis

### What Works Well
1. **Earthly builds**: Each agent has reproducible Earthfile builds
2. **GitHub Actions**: Existing `build.yml` workflow builds and pushes images on merge to main
3. **Flux GitOps**: Changes to `gitops/` are auto-deployed to the cluster
4. **Version in pyproject.toml**: Each agent has a version field (e.g., `version = "0.1.0"`)

### Current Gaps
1. **PR-based GitOps updates**: The `update-gitops` job creates PRs for manifest updates, adding friction
2. **Hardcoded agent list**: Only k8s-monitor is in build.yml, news-monitor missing
3. **core-agents dependency**: When core-agents changes, dependent agents should rebuild
4. **Image tag drift**: Manifests use `latest` which defeats GitOps versioning
5. **No auto-discovery**: New agents require manual workflow updates

---

## Proposed Solution

### Design Principles
1. **Commits and merges both work**: Workflow triggers on any push to main (direct or PR merge)
2. **Version from pyproject.toml**: Use semantic version from each agent's pyproject.toml
3. **Auto-discover agents**: Scan `agents/*/Earthfile` to find all agents dynamically
4. **Core triggers all**: Changes to `agents/core/` rebuild ALL dependent agents
5. **Immutable tags**: Format `{version}-{sha7}` (e.g., `0.1.0-abc1234`)

---

## Implementation Plan

### Phase 1: Dynamic Agent Discovery & Versioning

#### 1.1 Agent Discovery Script

Create a reusable script that discovers agents and extracts versions:

```bash
# scripts/discover-agents.sh
#!/bin/bash
# Discovers all agents under agents/ that have an Earthfile
# Outputs JSON: [{"name": "k8s-monitor", "version": "0.1.0", "path": "agents/k8s-monitor"}, ...]

set -e

agents_json="[]"

for earthfile in agents/*/Earthfile; do
    agent_dir=$(dirname "$earthfile")
    agent_name=$(basename "$agent_dir")

    # Skip 'core' - it's a library, not a deployable agent
    if [ "$agent_name" = "core" ]; then
        continue
    fi

    # Extract version from pyproject.toml
    pyproject="$agent_dir/pyproject.toml"
    if [ -f "$pyproject" ]; then
        version=$(grep '^version = ' "$pyproject" | head -1 | sed 's/version = "\(.*\)"/\1/')
    else
        version="0.0.0"
    fi

    # Check if gitops deployment exists
    has_deployment="false"
    if [ -f "gitops/apps/ai-agents/$agent_name/deployment.yaml" ]; then
        has_deployment="true"
    fi

    agents_json=$(echo "$agents_json" | jq -c --arg name "$agent_name" \
        --arg version "$version" \
        --arg path "$agent_dir" \
        --arg has_deployment "$has_deployment" \
        '. += [{"name": $name, "version": $version, "path": $path, "has_deployment": ($has_deployment == "true")}]')
done

echo "$agents_json"
```

#### 1.2 Updated GitHub Actions Workflow

```yaml
name: Build and Deploy Agents

on:
  push:
    branches: [main]
    paths:
      - 'agents/**'
      - 'Earthfile'
      - '.github/workflows/build.yml'
  workflow_dispatch:
    inputs:
      agent:
        description: 'Agent to build (leave empty for changed agents only, "all" for everything)'
        required: false
        default: ''
      force:
        description: 'Force rebuild even if no changes detected'
        required: false
        default: 'false'
        type: boolean

env:
  REGISTRY: registry.almckay.io

jobs:
  # ============================================================================
  # Discover agents and detect changes
  # ============================================================================
  discover:
    name: Discover Agents & Changes
    runs-on: ubuntu-latest
    outputs:
      agents: ${{ steps.discover.outputs.agents }}
      core_changed: ${{ steps.changes.outputs.core }}
      changed_agents: ${{ steps.changes.outputs.changed_agents }}
      build_matrix: ${{ steps.matrix.outputs.matrix }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2  # Need previous commit to detect changes

      - name: Discover all agents
        id: discover
        run: |
          # Find all agents with Earthfiles (excluding core)
          agents_json="[]"
          for earthfile in agents/*/Earthfile; do
              agent_dir=$(dirname "$earthfile")
              agent_name=$(basename "$agent_dir")

              [ "$agent_name" = "core" ] && continue

              # Extract version from pyproject.toml
              pyproject="$agent_dir/pyproject.toml"
              version="0.0.0"
              if [ -f "$pyproject" ]; then
                  version=$(grep '^version = ' "$pyproject" | head -1 | sed 's/version = "\(.*\)"/\1/')
              fi

              agents_json=$(echo "$agents_json" | jq -c --arg name "$agent_name" \
                  --arg version "$version" \
                  --arg path "$agent_dir" \
                  '. += [{"name": $name, "version": $version, "path": $path}]')
          done

          echo "agents=$agents_json" >> $GITHUB_OUTPUT
          echo "Discovered agents: $agents_json"

      - name: Detect changes
        id: changes
        run: |
          # Check if core changed
          if git diff --name-only HEAD~1 HEAD | grep -q '^agents/core/'; then
              echo "core=true" >> $GITHUB_OUTPUT
              echo "Core agents changed - all dependent agents will rebuild"
          else
              echo "core=false" >> $GITHUB_OUTPUT
          fi

          # Find which agents changed
          changed="[]"
          for agent_dir in agents/*/; do
              agent_name=$(basename "$agent_dir")
              [ "$agent_name" = "core" ] && continue

              if git diff --name-only HEAD~1 HEAD | grep -q "^agents/$agent_name/"; then
                  changed=$(echo "$changed" | jq -c --arg name "$agent_name" '. += [$name]')
              fi
          done

          echo "changed_agents=$changed" >> $GITHUB_OUTPUT
          echo "Changed agents: $changed"

      - name: Build matrix
        id: matrix
        run: |
          AGENTS='${{ steps.discover.outputs.agents }}'
          CORE_CHANGED='${{ steps.changes.outputs.core }}'
          CHANGED='${{ steps.changes.outputs.changed_agents }}'
          FORCE='${{ github.event.inputs.force }}'
          SPECIFIC='${{ github.event.inputs.agent }}'

          if [ "$SPECIFIC" = "all" ] || [ "$FORCE" = "true" ]; then
              # Build all agents
              matrix="$AGENTS"
          elif [ -n "$SPECIFIC" ]; then
              # Build specific agent
              matrix=$(echo "$AGENTS" | jq -c --arg name "$SPECIFIC" '[.[] | select(.name == $name)]')
          elif [ "$CORE_CHANGED" = "true" ]; then
              # Core changed - build all agents
              matrix="$AGENTS"
              echo "Core changed, rebuilding all agents"
          else
              # Only build changed agents
              matrix=$(echo "$AGENTS" | jq -c --argjson changed "$CHANGED" \
                  '[.[] | select(.name as $n | $changed | index($n))]')
          fi

          # Skip if nothing to build
          if [ "$matrix" = "[]" ]; then
              echo "No agents to build"
              matrix="[]"
          fi

          echo "matrix=$matrix" >> $GITHUB_OUTPUT
          echo "Build matrix: $matrix"

  # ============================================================================
  # Build core-agents first (if changed)
  # ============================================================================
  build-core:
    name: Build Core Agents
    runs-on: ubuntu-latest
    needs: discover
    if: needs.discover.outputs.core_changed == 'true' || github.event.inputs.force == 'true'

    steps:
      - uses: actions/checkout@v4

      - name: Setup Earthly
        uses: earthly/actions-setup@v1
        with:
          version: v0.8.15

      - name: Log in to Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}

      - name: Build and push core-agents
        run: |
          earthly --push --ci ./agents/core+push

  # ============================================================================
  # Build agent images (parallel matrix)
  # ============================================================================
  build-agents:
    name: Build ${{ matrix.agent.name }}
    runs-on: ubuntu-latest
    needs: [discover, build-core]
    if: always() && needs.discover.outputs.build_matrix != '[]' && needs.discover.result == 'success'
    strategy:
      fail-fast: false
      matrix:
        agent: ${{ fromJson(needs.discover.outputs.build_matrix) }}

    outputs:
      built_agents: ${{ steps.record.outputs.built }}

    steps:
      - uses: actions/checkout@v4

      - name: Setup Earthly
        uses: earthly/actions-setup@v1
        with:
          version: v0.8.15

      - name: Log in to Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}

      - name: Build version tag
        id: version
        run: |
          SHA_SHORT=${GITHUB_SHA::7}
          VERSION="${{ matrix.agent.version }}-${SHA_SHORT}"
          echo "tag=$VERSION" >> $GITHUB_OUTPUT
          echo "Building ${{ matrix.agent.name }}:$VERSION"

      - name: Build and push
        run: |
          earthly \
            --push \
            --ci \
            --build-arg VERSION=${{ steps.version.outputs.tag }} \
            ./${{ matrix.agent.path }}+push

      - name: Record built agent
        id: record
        run: |
          echo "built=${{ matrix.agent.name }}:${{ steps.version.outputs.tag }}" >> $GITHUB_OUTPUT

  # ============================================================================
  # Update GitOps manifests
  # ============================================================================
  update-gitops:
    name: Update GitOps Manifests
    runs-on: ubuntu-latest
    needs: [discover, build-agents]
    if: always() && needs.build-agents.result == 'success'
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          fetch-depth: 1

      - name: Update deployment manifests
        run: |
          SHA_SHORT=${GITHUB_SHA::7}
          AGENTS='${{ needs.discover.outputs.build_matrix }}'

          echo "Updating manifests for agents: $AGENTS"

          # Update each built agent's deployment
          echo "$AGENTS" | jq -r '.[] | "\(.name) \(.version)"' | while read name version; do
              DEPLOY_FILE="gitops/apps/ai-agents/${name}/deployment.yaml"

              if [ -f "$DEPLOY_FILE" ]; then
                  TAG="${version}-${SHA_SHORT}"
                  echo "Updating $name to $TAG"

                  # Update all image references for this agent
                  sed -i "s|registry.almckay.io/${name}:[^ ]*|registry.almckay.io/${name}:${TAG}|g" "$DEPLOY_FILE"
              else
                  echo "Warning: No deployment found for $name at $DEPLOY_FILE"
              fi
          done

      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          git add gitops/

          if git diff --staged --quiet; then
              echo "No manifest changes to commit"
          else
              SHA_SHORT=${GITHUB_SHA::7}
              git commit -m "chore(gitops): update agent images [${SHA_SHORT}] [skip ci]"
              git push
              echo "Manifests updated and pushed"
          fi

  # ============================================================================
  # Create GitHub release (on tags only)
  # ============================================================================
  release:
    name: Create Release
    runs-on: ubuntu-latest
    needs: [discover, build-agents]
    if: startsWith(github.ref, 'refs/tags/v')
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate release notes
        id: notes
        run: |
          AGENTS='${{ needs.discover.outputs.agents }}'
          SHA_SHORT=${GITHUB_SHA::7}

          # Build release body
          body="## Agent Images\n\n"
          echo "$AGENTS" | jq -r '.[] | "\(.name) \(.version)"' | while read name version; do
              body+="**${name}:** \`registry.almckay.io/${name}:${version}-${SHA_SHORT}\`\n"
          done

          echo "body<<EOF" >> $GITHUB_OUTPUT
          echo -e "$body" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          body: ${{ steps.notes.outputs.body }}
          generate_release_notes: true
```

---

### Phase 2: Update Root Earthfile for Dynamic Builds

The root Earthfile should support building any discovered agent:

```earthly
VERSION 0.8

# Global arguments
ARG --global REGISTRY=registry.almckay.io
ARG --global PYTHON_VERSION=3.11
ARG --global VERSION=latest

# =============================================================================
# Shared Base Images (unchanged)
# =============================================================================

python-base:
    FROM python:${PYTHON_VERSION}-slim
    WORKDIR /app
    RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc curl && rm -rf /var/lib/apt/lists/*
    RUN useradd -m -u 1000 agent
    SAVE IMAGE --cache-hint

python-k8s-base:
    FROM +python-base
    ARG TARGETARCH
    RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" \
        && chmod +x kubectl && mv kubectl /usr/local/bin/
    SAVE IMAGE --cache-hint

# =============================================================================
# Core Agents Library
# =============================================================================

core-agents:
    BUILD ./agents/core+build

core-agents-push:
    BUILD ./agents/core+push

core-agents-test:
    BUILD ./agents/core+test

core-agents-lint:
    BUILD ./agents/core+lint

# =============================================================================
# Dynamic Agent Targets
# =============================================================================
# These targets work with any agent under agents/

# Build any agent by name
agent:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+docker

# Push any agent by name
agent-push:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+push

# Test any agent by name
agent-test:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+test

# Lint any agent by name
agent-lint:
    ARG AGENT_NAME
    BUILD ./agents/${AGENT_NAME}+lint

# =============================================================================
# Orchestration (builds all known agents)
# =============================================================================

# Push all (core + all agents)
push-all:
    BUILD +core-agents-push
    BUILD ./agents/k8s-monitor+push
    BUILD ./agents/news-monitor+push

# Test all
test-all:
    BUILD +core-agents-test
    BUILD ./agents/k8s-monitor+test
    BUILD ./agents/news-monitor+test

# Lint all
lint-all:
    BUILD +core-agents-lint
    BUILD ./agents/k8s-monitor+lint
    BUILD ./agents/news-monitor+lint

# Full CI pipeline
ci:
    BUILD +lint-all
    BUILD +test-all
```

---

## Versioning Strategy

### Image Tag Format

| Scenario | Tag Format | Example |
|----------|-----------|---------|
| Push/merge to main | `{pyproject.version}-{sha7}` | `0.1.0-abc1234` |
| Git tag `v*` | `{pyproject.version}` | `0.1.0` |
| Manual/branch build | `{pyproject.version}-{branch}-{sha7}` | `0.1.0-feature-xyz-def5678` |

### Version Bump Workflow

When releasing a new version:

1. Update `version` in agent's `pyproject.toml`
2. Commit: `chore(k8s-monitor): bump version to 0.2.0`
3. Merge to main → builds `0.2.0-{sha}`
4. Optionally tag: `git tag v0.2.0` → builds `0.2.0`

---

## Dependency Graph

```
agents/core/  ─────────────┐
    │                      │
    ├──────────────────────┼────────────────────┐
    │                      │                    │
    ▼                      ▼                    ▼
agents/k8s-monitor/   agents/news-monitor/   (future agents)
```

**Rule**: If `agents/core/` changes, ALL agents rebuild.

This is enforced in the workflow:
```yaml
if [ "$CORE_CHANGED" = "true" ]; then
    matrix="$AGENTS"  # Build all
fi
```

---

## File Changes Summary

### Files to Modify

| File | Changes |
|------|---------|
| `.github/workflows/build.yml` | Complete rewrite with discovery, matrix builds |
| `Earthfile` | Add dynamic agent targets, news-monitor |
| `gitops/apps/ai-agents/*/deployment.yaml` | Will be auto-updated by CI |

### Files to Create

| File | Purpose |
|------|---------|
| `scripts/discover-agents.sh` | (Optional) Standalone discovery script |

---

## Adding a New Agent

With this system, adding a new agent is simple:

1. Create `agents/my-new-agent/` with:
   - `Earthfile` (following the template pattern)
   - `pyproject.toml` with `version = "0.1.0"`
   - `src/` directory

2. Create `gitops/apps/ai-agents/my-new-agent/deployment.yaml`

3. Push to main

The CI will automatically:
- Discover the new agent
- Build and push the image
- Update the manifest with the versioned tag
- Flux deploys it

No workflow file changes needed!

---

## Rollback Process

### Quick Rollback via Git

```bash
# Find the previous working version
git log --oneline gitops/apps/ai-agents/k8s-monitor/deployment.yaml

# Revert to previous manifest
git checkout abc1234 -- gitops/apps/ai-agents/k8s-monitor/deployment.yaml
git commit -m "chore(gitops): rollback k8s-monitor to 0.1.0-abc1234"
git push

# Flux auto-syncs the rollback
```

### Rollback via kubectl (immediate)

```bash
KUBECONFIG=/home/al/.kube/config kubectl set image deployment/k8s-monitor \
    worker=registry.almckay.io/k8s-monitor:0.1.0-abc1234 \
    -n ai-agents
```

---

## Questions Resolved

| Question | Answer |
|----------|--------|
| Direct commits vs merges? | Both work - workflow triggers on any push to main |
| Version source? | `pyproject.toml` version field |
| Hardcoded agent list? | No - auto-discovered from `agents/*/Earthfile` |
| Core dependency? | Core changes trigger all agent rebuilds |
| Retention policy? | Deferred to future discussion |

---

## Next Steps

1. **Review this plan** - Any adjustments needed?
2. **Implement Phase 1** - Update workflow and Earthfile
3. **Test with a small change** - Verify the pipeline works end-to-end
4. **Document** - Update CLAUDE.md with new CI/CD patterns
