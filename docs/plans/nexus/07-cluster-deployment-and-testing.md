
# Kubani Nexus: Cluster Deployment and Testing Plan

**Document Status:** DRAFT
**Author:** Manus AI
**Date:** 2026-02-06

## 1. Introduction

This document provides a highly detailed, step-by-step guide for deploying, configuring, and testing the Kubani Nexus system on the `kubani` Kubernetes cluster. It is intended for a developer with `kubectl` access and a foundational understanding of Kubernetes and the existing `kubani` GitOps workflow.

This plan covers the work that could not be completed in the local sandbox environment due to resource constraints, specifically:

-   Deployment of the OCI registry (Harbor).
-   Full end-to-end integration testing with all services running simultaneously.
-   Configuration of the frontend UI to connect to the new Nexus Gateway.

Following this plan meticulously will ensure a smooth and successful rollout of the Nexus system.

## 2. Prerequisites

Before you begin, ensure you have the following:

-   `kubectl` configured to access the `kubani` cluster.
-   `gh` (GitHub CLI) authenticated and configured.
-   Local clone of the `X-McKay/kubani` repository, with the `feature/kubani-nexus` branch checked out.
-   Permissions to push changes to the `infrastructure` repository that manages the cluster's GitOps.

## 3. Phase 1: Infrastructure Setup (Harbor OCI Registry)

**Goal:** Deploy a Harbor instance to serve as the OCI registry for skills.

### Step 3.1: Create Harbor Kubernetes Manifests

We will use the official Harbor Helm chart to generate the Kubernetes manifests. This provides a battle-tested and configurable starting point.

1.  **Add the Harbor Helm repository:**

    ```bash
    helm repo add harbor https://helm.goharbor.io
    helm repo update
    ```

2.  **Create a `harbor-values.yaml` file.** This file will configure our Harbor instance. Create it at `infrastructure/gitops/manifests/harbor/values.yaml`:

    ```yaml
    # infrastructure/gitops/manifests/harbor/values.yaml

    expose:
      type: ingress
      tls:
        enabled: true
        certSource: secret
        secret:
          secretName: harbor-tls-cert
      ingress:
        hosts:
          core: harbor.kubani.local  # Use a local-only domain
        controller: "k8s.io/ingress-nginx"
        annotations:
          nginx.ingress.kubernetes.io/proxy-body-size: "0"
          nginx.ingress.kubernetes.io/proxy-read-timeout: "600"

    externalURL: https://harbor.kubani.local

    persistence:
      enabled: true
      resourcePolicy: "keep"
      persistentVolumeClaim:
        registry:
          size: 20Gi
        chartmuseum:
          size: 5Gi
        jobservice:
          size: 1Gi
        database:
          size: 10Gi
        redis:
          size: 1Gi

    # Use internal PostgreSQL from the chart
    database:
      type: internal

    # Use internal Redis from the chart
    redis:
      type: internal

    # Disable services we don't need
    notary:
      enabled: false
    trivy:
      enabled: true # Keep Trivy for vulnerability scanning
    ```

3.  **Generate the manifests using Helm:**

    ```bash
    helm template harbor harbor/harbor \
      -f infrastructure/gitops/manifests/harbor/values.yaml \
      --namespace harbor > infrastructure/gitops/manifests/harbor/release.yaml
    ```

4.  **Create the `harbor` namespace manifest:**

    ```yaml
    # infrastructure/gitops/manifests/harbor/namespace.yaml
    apiVersion: v1
    kind: Namespace
    metadata:
      name: harbor
    ```

### Step 3.2: Commit and Deploy via GitOps

1.  **Add the new manifests to your GitOps repository (`infrastructure`).**
2.  **Commit the changes:**

    ```bash
    git add manifests/harbor/
    git commit -m "feat: add Harbor OCI registry for Nexus skills"
    git push
    ```

3.  **Verify deployment.** ArgoCD (or your GitOps controller) will pick up the changes and deploy Harbor. Monitor the deployment:

    ```bash
    kubectl get pods -n harbor -w
    ```

    Wait until all pods are in the `Running` state.

### Step 3.3: Configure Harbor

1.  **Access the Harbor UI.** Since we used `harbor.kubani.local`, you will need to add a local DNS entry (`/etc/hosts`) to point this domain to your cluster's ingress IP.

2.  **Log in.** The default admin password can be retrieved from the `harbor-core` secret:

    ```bash
    kubectl get secret harbor-core -n harbor -o jsonpath="{.data.HARBOR_ADMIN_PASSWORD}" | base64 --decode
    ```

3.  **Create a project.** Create a new **public** project named `nexus-skills`.

4.  **Create a robot account.** Under the `nexus-skills` project, go to `Robot Accounts` and create a new robot account named `nexus-worker` with permissions to **push and pull artifacts**.

5.  **Save the credentials.** Securely store the robot account name and token. These will be used by the Nexus Orchestrator.

## 4. Phase 2: Deploying Nexus Components

**Goal:** Deploy the new Nexus services to the cluster and configure them.

### Step 4.1: Create Kubernetes Deployment Manifests

We will create deployment manifests for the two new long-running services: the **Nexus Orchestrator Worker** and the **Nexus Conversational Gateway**.

1.  **Create `nexus-orchestrator-deployment.yaml`:**

    ```yaml
    # infrastructure/gitops/manifests/nexus/orchestrator-deployment.yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: nexus-orchestrator
      namespace: kubani
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: nexus-orchestrator
      template:
        metadata:
          labels:
            app: nexus-orchestrator
        spec:
          containers:
          - name: worker
            image: your-registry/kubani-nexus:latest # Replace with your image
            command: ["python", "-m", "kubani.nexus.orchestrator.worker"]
            env:
            - name: NEXUS_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: nexus-secrets
                  key: DATABASE_URL
            - name: TEMPORAL_SERVER_URL
              value: "temporal-frontend.temporal.svc.cluster.local:7233"
            - name: NEXUS_REDIS_URL
              value: "redis://redis-master.redis.svc.cluster.local:6379"
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: openai-api-key
                  key: api_key
            - name: NEXUS_SKILL_REGISTRY_URL
              value: "https://harbor.kubani.local"
            - name: NEXUS_SKILL_ROBOT_USER
              valueFrom:
                secretKeyRef:
                  name: nexus-secrets
                  key: HARBOR_ROBOT_USER
            - name: NEXUS_SKILL_ROBOT_SECRET
              valueFrom:
                secretKeyRef:
                  name: nexus-secrets
                  key: HARBOR_ROBOT_SECRET
    ```

2.  **Create `nexus-gateway-deployment.yaml`:**

    ```yaml
    # infrastructure/gitops/manifests/nexus/gateway-deployment.yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: nexus-gateway
      namespace: kubani
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: nexus-gateway
      template:
        metadata:
          labels:
            app: nexus-gateway
        spec:
          containers:
          - name: gateway
            image: your-registry/kubani-nexus:latest # Replace with your image
            command: ["uvicorn", "kubani.nexus.gateway.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
            ports:
            - containerPort: 8000
            env:
            - name: NEXUS_DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: nexus-secrets
                  key: DATABASE_URL
            - name: TEMPORAL_SERVER_URL
              value: "temporal-frontend.temporal.svc.cluster.local:7233"
            - name: NEXUS_REDIS_URL
              value: "redis://redis-master.redis.svc.cluster.local:6379"
            - name: DISCORD_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: discord-bot-token
                  key: token
    ---
    apiVersion: v1
    kind: Service
    metadata:
      name: nexus-gateway
      namespace: kubani
    spec:
      selector:
        app: nexus-gateway
      ports:
      - protocol: TCP
        port: 80
        targetPort: 8000
    ```

3.  **Create `nexus-secrets.yaml`:**

    This manifest should be created locally and applied manually with `kubectl`, **NOT** committed to GitOps for security.

    ```yaml
    # nexus-secrets.yaml (DO NOT COMMIT)
    apiVersion: v1
    kind: Secret
    metadata:
      name: nexus-secrets
      namespace: kubani
    type: Opaque
    stringData:
      DATABASE_URL: "postgresql://kubani:YOUR_PASSWORD@postgres.db.svc.cluster.local:5432/kubani_nexus"
      HARBOR_ROBOT_USER: "robot$nexus-worker"
      HARBOR_ROBOT_SECRET: "YOUR_HARBOR_ROBOT_SECRET"
    ```

### Step 4.2: Build and Push Docker Image

1.  **Create a `Dockerfile` in the root of the `kubani` repository.**

    ```dockerfile
    # Dockerfile
    FROM python:3.11-slim

    WORKDIR /app

    # Install poetry
    RUN pip install poetry

    # Copy only pyproject.toml and poetry.lock to leverage Docker layer caching
    COPY pyproject.toml poetry.lock* ./

    # Install dependencies
    RUN poetry config virtualenvs.create false && \
        poetry install --no-dev --no-interaction --no-ansi

    # Copy the rest of the application code
    COPY . .

    # Expose the gateway port
    EXPOSE 8000

    # Default command (can be overridden in Kubernetes manifests)
    CMD ["python", "-m", "kubani.nexus.gateway.app"]
    ```

2.  **Build and push the image:**

    ```bash
    docker build -t your-registry/kubani-nexus:latest .
    docker push your-registry/kubani-nexus:latest
    ```

### Step 4.3: Deploy via GitOps

1.  **Commit the deployment and service manifests** to your GitOps repository.
2.  **Manually apply the secrets:**

    ```bash
    kubectl apply -f nexus-secrets.yaml
    ```

3.  **Verify deployment:**

    ```bash
    kubectl get pods -n kubani -l "app in (nexus-orchestrator, nexus-gateway)" -w
    ```

## 5. Phase 3: End-to-End Testing

**Goal:** Perform a comprehensive end-to-end test of the entire system.

### Test Case 5.1: UI to Agent and Back

1.  **Configure the UI:** Update the frontend configuration to point the chat WebSocket to the new `nexus-gateway` service.
2.  **Send a message:** From the Kubani UI, send a simple message like "Hello".
3.  **Verify:**
    -   The message appears in the UI.
    -   The `nexus-gateway` logs show a new WebSocket connection and message received.
    -   The `nexus-orchestrator` logs show a new workflow execution or signal.
    -   The agent responds with a greeting.
    -   The response appears in the UI.

### Test Case 5.2: Discord to Agent and Back

1.  **Invite the bot:** Ensure the Discord bot (using the configured token) is in a test channel.
2.  **Send a message:** Mention the bot in the channel with a message.
3.  **Verify:**
    -   The `nexus-gateway` logs show a message received from the Discord bridge.
    -   The `nexus-orchestrator` logs show a workflow signal.
    -   The agent responds in the Discord channel.

### Test Case 5.3: Skill Synthesis and Execution

1.  **Give a novel task:** From either UI or Discord, give the agent a task it cannot perform with existing skills, e.g., "What is the hexadecimal representation of the color lavender?"
2.  **Verify:**
    -   **Orchestrator:** Logs show it's delegating to the `SkillSynthesizer`.
    -   **LLM:** (If you have access to logs) An LLM call is made to generate the skill.
    -   **Orchestrator:** Logs show it's registering the new skill.
    -   **Harbor UI:** A new artifact appears in the `nexus-skills` repository.
    -   **Database:** A new entry appears in the `skills` table.
    -   **Orchestrator:** Logs show the new skill is executed.
    -   **Agent:** The agent responds with the correct answer (`#E6E6FA`).

### Test Case 5.4: HITL Approval Workflow

1.  **Give a risky task:** Give the agent a task that requires a medium-risk skill, e.g., "Check if the website `example.com` is up by making a HEAD request."
2.  **Verify:**
    -   **Synthesizer:** A skill using `requests` is generated.
    -   **Registry:** The skill is registered with `pending_review` status.
    -   **Database:** A new entry appears in the `approval_requests` table.
    -   **UI:** The "Approvals" panel shows a new pending request.
    -   **Agent:** The agent responds that the skill requires approval.
3.  **Approve the skill:** Use the UI to approve the request.
4.  **Re-run the task:** Give the agent the same task again.
5.  **Verify:**
    -   The agent now executes the skill and provides the answer.

## 6. Conclusion

Once these phases are complete and all tests pass, the Kubani Nexus system will be fully deployed and operational. The final step is to merge the `feature/kubani-nexus` branch into `main` and clean up any temporary resources.
