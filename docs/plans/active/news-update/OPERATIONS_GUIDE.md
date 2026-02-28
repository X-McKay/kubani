# News Digest Syndicate: Operations Guide

This guide provides a comprehensive overview of how to test, deploy, and validate the `news-digest` syndicate locally and in a cluster environment. It is intended for developers and operators responsible for maintaining the system.

---

## 1. Local Testing

All components of the three-stage pipeline can be tested locally without needing a full Temporal cluster. The test suite is designed to run quickly and verify the logic of each workflow and activity in isolation.

### 1.1. Prerequisites

- Python 3.11+
- `pip` and `uv`
- An active Python virtual environment

### 1.2. Setup

1.  **Install Dependencies**: From the root of the `kubani` repository, install all required dependencies. This includes `pytest` and its plugins.

    ```bash
    # It is recommended to use a virtual environment
    python3.11 -m venv .venv
    source .venv/bin/activate

    # Install dependencies
    pip install -e .[dev]
    ```

2.  **Set Environment**: The tests run against the local filesystem and do not require external services. The `PYTHONPATH` must be set to include the project root so that imports like `kubani.framework` resolve correctly.

    ```bash
    export PYTHONPATH="/path/to/your/kubani:$PYTHONPATH"
    ```

### 1.3. Running Tests

Execute the test suite using `pytest`. The `-v` flag provides verbose output.

```bash
# From the root of the kubani repository
pytest kubani/syndicates/news_digest/tests/ -v
```

**Expected Output**: You should see `134 passed` in the test summary. This confirms that all data models, pure functions, and workflow/activity logic are correct.

| Test File                  | Tests | Coverage                                                              |
| :------------------------- | :---- | :-------------------------------------------------------------------- |
| `test_models.py`           | 62    | All data models, conversion functions, and JSON parsing utilities.    |
| `test_ingest_workflows.py` | 39    | Initialization, data conversion, and child workflow triggers.         |
| `test_analyze_workflow.py` | 9     | Initialization, result building, and query methods.                   |
| `test_digest_workflow.py`  | 19    | Section-based composition, prompt building, and fallback logic.       |
| `test_worker.py`           | 5     | Correct registration of all activities and workflows.                 |

---

## 2. Cluster Deployment & Validation

Deploying to a cluster involves building the syndicate image, pushing it to a registry, and ensuring the Temporal cluster can pull it. Validation requires interacting with the Temporal UI and checking external services like Discord.

### 2.1. Prerequisites

- Docker and a container registry (e.g., Docker Hub, ECR, GCR)
- `kubectl` configured to access your Kubernetes cluster
- A running Temporal cluster
- A running instance of the **Memory MCP server** (Qdrant, Neo4j, Redis)
- Configured Discord webhook for the `ai-news` channel

### 2.2. Deployment Steps

1.  **Build and Push the Image**: The `news_digest` syndicate is containerized. Build the image using its `Earthfile` and push it to your container registry.

    ```bash
    # From kubani/syndicates/news_digest/
    earthly +build --push
    ```

2.  **Deploy to Kubernetes**: Apply the Kubernetes deployment manifest for the syndicate. This will create a deployment for the Temporal worker.

    ```bash
    # From kubani/syndicates/news_digest/
    kubectl apply -f k8s/deployment.yaml
    ```

3.  **Set up Schedules**: The worker will start, but the workflows will not run until their schedules are created in Temporal. Use the `news-digest-schedules` CLI to do this. You only need to do this once.

    ```bash
    # Exec into the running worker pod
    kubectl exec -it <news-digest-worker-pod-name> -- /bin/bash

    # Inside the pod, run the setup command
    news-digest-schedules setup
    ```

    This command is idempotent. It will create or update the four required schedules:
    - `news-rss-ingest-schedule` (every 30 min)
    - `news-arxiv-ingest-schedule` (every 4 hours)
    - `news-github-ingest-schedule` (every 6 hours)
    - `news-digest-schedule` (9 AM & 9 PM daily)

### 2.3. Validation

Validation involves observing the system to ensure each stage of the pipeline is executing correctly.

#### **Step 1: Verify Ingest Workflows**

1.  **Check Schedules**: In the Temporal UI for the `news-digest` namespace, navigate to the **Schedules** page. You should see the four schedules listed with their next run times.

2.  **Trigger Manually**: To test immediately, you can manually trigger an ingest workflow. Click on the `news-rss-ingest-schedule` and select **"Trigger Immediately"**.

3.  **Observe Workflow Execution**:
    - A new `RSSIngestWorkflow` run should appear in the **Workflows** list.
    - Click on it to view its progress. It should execute its activities (`collect_feeds_activity`, `batch_check_duplicates_activity`, `store_raw_documents_activity`) and complete within a few minutes.
    - **Crucially**, check the **Child Workflows** tab. You should see a new `AnalyzeDocumentWorkflow` run that was started by the ingest workflow.

#### **Step 2: Verify Analyze Workflow**

1.  **Observe Child Workflow**: Navigate to the `AnalyzeDocumentWorkflow` run that was triggered.
2.  **Check Activities**: It will execute `analyze_document_activity` and `store_analyzed_document_activity` for each new document. You can inspect the input/output of these activities to see the extracted entities, topics, and summaries.
3.  **Verify Graph Data (Optional)**: If you have access to the Neo4j browser, you can query the graph to verify that `AnalyzedDocument` nodes were created with `MENTIONS` and `DISCUSSES` relationships to `Entity` and `Topic` nodes.

#### **Step 3: Verify Digest Workflow**

1.  **Trigger Manually**: Trigger the `news-digest-schedule` manually from the Temporal UI.
2.  **Observe Section Generation**: The `NewsDigestWorkflow` will start. It will first query for documents, then execute `run_agent_activity` multiple times—once for each section ("Top Stories", "Research Spotlight", "Tool Spotlight").
3.  **Observe Synthesis**: After the sections are generated, a final `run_agent_activity` is called to synthesize the final digest.
4.  **Check Discord**: The final digest should be posted to the configured Discord channel (`#ai-news` by default).
5.  **Check UI Activity**: A summary of the digest should appear in the UI activity feed.

By following these steps, you can validate that the entire pipeline is functioning correctly from end to end.
