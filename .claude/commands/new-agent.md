# Create New AI Agent

Scaffold a new AI agent using the Copier template system.

## Instructions

Help the user create a new AI agent by gathering requirements and running the Copier template.

### Step 1: Gather Agent Requirements

Ask the user about their new agent:

1. **Agent Name**: What should the agent be called? (lowercase, hyphens only, e.g., `backup-manager`)
2. **Description**: Brief description of what the agent does
3. **Features needed**:
   - Does it need Kubernetes API access?
   - Does it need Temporal for workflow orchestration?
   - Does it need Discord notifications?
   - Does it need LLM capabilities?
4. **If Kubernetes access needed**: Read-only or read-write permissions?
5. **Schedule Type**: Continuous (long-running) or scheduled (triggered by cron)?
6. **Resource Requirements**: Small (100m CPU, 256Mi), Medium (500m, 512Mi), or Large (1000m, 1Gi)?

### Step 2: Run Copier Template

Once requirements are gathered, run Copier to generate the agent:

```bash
cd /home/al/git/kubani
copier copy templates/agent agents/ --data agent_name=<name> --data description="<description>" ...
```

Or run interactively:

```bash
cd /home/al/git/kubani
copier copy templates/agent agents/
```

### Step 3: Post-Generation Setup

After generating the agent:

1. **Review generated files**:
   ```bash
   ls -la agents/<agent-name>/
   ls -la gitops/apps/ai-agents/<agent-name>/
   ```

2. **If using Discord**, create and encrypt the secret:
   ```bash
   cd gitops/apps/ai-agents/<agent-name>/
   # Edit secret.enc.yaml with actual webhook URL
   sops --encrypt --age $(cat /home/al/git/kubani/age.pub) secret.yaml > secret.enc.yaml
   rm secret.yaml
   ```

3. **Install dependencies locally** for development:
   ```bash
   cd agents/<agent-name>
   uv sync
   ```

4. **Run tests** to verify scaffold:
   ```bash
   cd agents/<agent-name>
   uv run pytest
   ```

5. **Build Docker image**:
   ```bash
   cd /home/al/git/kubani
   earthly ./agents/<agent-name>+docker
   ```

6. **Push to registry**:
   ```bash
   earthly ./agents/<agent-name>+push
   ```

### Step 4: Implement Agent Logic

Guide the user to implement their agent:

1. **Define tools** in `src/<package_name>/tools.py`:
   - Add functions decorated with `@tool` from strands-agents
   - Each tool should do one thing well

2. **Create agent** in `src/<package_name>/agent.py`:
   - Configure the agent with appropriate tools
   - Set system prompt for the agent's behavior

3. **Implement workflows** in `src/<package_name>/workflows.py`:
   - Define Temporal workflows for orchestration
   - Use activities for side effects

4. **Add activities** in `src/<package_name>/activities.py`:
   - Wrap agent invocations in activities
   - Add any external API calls as activities

### Step 5: Deploy to Cluster

1. **Add to Flux kustomization** in `gitops/apps/ai-agents/kustomization.yaml`:
   ```yaml
   resources:
     - ./k8s-monitor
     - ./<agent-name>  # Add your new agent
   ```

2. **Commit and push**:
   ```bash
   git add agents/<agent-name> gitops/apps/ai-agents/<agent-name>
   git commit -m "feat: Add <agent-name> agent"
   git push
   ```

3. **Verify deployment**:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=<agent-name>
   ```

## Template Features

The agent template includes:

- **Strands Agents SDK** for AI tool orchestration
- **Temporal** for durable workflow execution (optional)
- **Kubernetes client** for cluster operations (optional)
- **Discord integration** for notifications (optional)
- **Self-hosted LLM** via vLLM (optional)
- **Earthly build** with multi-architecture support
- **GitOps manifests** for Flux CD deployment
- **Pytest tests** with fixtures and mocking patterns

## Example: Creating a Log Analyzer Agent

```bash
copier copy templates/agent agents/ \
  --data agent_name=log-analyzer \
  --data package_name=log_analyzer \
  --data description="Analyzes application logs for errors and anomalies" \
  --data uses_kubernetes=true \
  --data uses_temporal=true \
  --data uses_discord=true \
  --data uses_llm=true \
  --data k8s_permissions=read \
  --data schedule_type=scheduled \
  --data cpu_request=100m \
  --data memory_request=256Mi \
  --data cpu_limit=500m \
  --data memory_limit=512Mi
```

## After Creating the Agent

Provide a summary including:
1. Files generated
2. Next steps for implementation
3. How to test locally
4. How to deploy to the cluster
