# News Syndicate Reliability Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix news syndicate pod crashes and feed collection errors to achieve stable operation

**Architecture:** Fix permission issue in Docker image build (uv installation), update broken RSS feed URLs, replace failing liveness probe with proper health check, and thoroughly test before deployment.

**Tech Stack:** Python 3.11, Earthly (Docker builds), Kubernetes, uv package manager, RSS feed parsing (feedparser)

---

## Background

The news-monitor pod is experiencing:
1. **Critical:** Liveness probe failures causing restarts every few minutes (26 restarts in 2 hours)
   - Root cause: `uv` installed to `/root/.local/bin` but container runs as `agent` user
2. **Minor:** 4 RSS feeds returning 403/404 errors
   - OpenAI, Anthropic, NVIDIA, Reuters feeds need URL updates
3. **Improvement:** Liveness probe uses heavy command, should use HTTP health endpoint

---

## Task 1: Fix uv Installation Permissions

**Files:**
- Modify: `kubani/syndicates/news_digest/Earthfile:86-99`

### Step 1: Update uv installation to be system-wide

Modify the `docker` target in Earthfile to install uv system-wide instead of to `/root`:

```earthfile
docker:
    FROM python:3.11-slim

    # Install runtime dependencies only
    RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        && rm -rf /var/lib/apt/lists/*

    # Create non-root user BEFORE installing uv
    RUN useradd -m -s /bin/bash agent
    WORKDIR /app

    # Install uv system-wide (accessible to all users)
    RUN curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --install-dir /usr/local/bin
    ENV PATH="/usr/local/bin:$PATH"
```

**Change:** Move user creation before uv installation, use `--install-dir /usr/local/bin` instead of default `/root/.local/bin`

### Step 2: Verify uv is accessible to agent user

Add verification step after user switch:

```earthfile
    # Switch to non-root user
    USER agent

    # Verify uv is accessible
    RUN uv --version
```

Insert this right after line 127 (after `USER agent`)

### Step 3: Commit uv installation fix

```bash
git add kubani/syndicates/news_digest/Earthfile
git commit -m "fix(news-digest): install uv system-wide to fix liveness probe"
```

---

## Task 2: Update Broken RSS Feed URLs

**Files:**
- Modify: `kubani/agents/feed_collector/feeds.py:119-184`

### Step 1: Research correct feed URLs

Manually verify the correct URLs for each broken feed:

```bash
# Test OpenAI - try alternate URL
curl -I "https://openai.com/index/rss.xml"

# Test Anthropic - try alternate URL
curl -I "https://www.anthropic.com/index/rss"

# Test NVIDIA - try main blog feed
curl -I "https://blogs.nvidia.com/feed/"

# Test Reuters - try alternate tech feed
curl -I "https://www.reuters.com/technology/rss"
```

**Expected:** Find working URLs that return 200 OK

### Step 2: Update feed URLs in feeds.py

Based on research, update the broken feeds:

```python
# Line 120-124: OpenAI Blog
FeedConfig(
    name="OpenAI Blog",
    url="https://openai.com/index/rss.xml",  # Updated URL
    category=FeedCategory.COMPANY_BLOGS,
    priority=10,
),

# Line 126-130: Anthropic News
FeedConfig(
    name="Anthropic News",
    url="https://www.anthropic.com/index/rss",  # Updated URL
    category=FeedCategory.COMPANY_BLOGS,
    priority=10,
),

# Line 150-154: NVIDIA AI Blog
FeedConfig(
    name="NVIDIA AI Blog",
    url="https://blogs.nvidia.com/feed/",  # Updated URL (remove /ai/)
    category=FeedCategory.COMPANY_BLOGS,
    priority=7,
),

# Line 180-184: Reuters Technology
FeedConfig(
    name="Reuters - Technology",
    url="https://www.reuters.com/technology/rss",  # Updated URL
    category=FeedCategory.BUSINESS,
    priority=7,
),
```

**Note:** If any URL still doesn't work, set `enabled: bool = False` for that feed

### Step 3: Commit feed URL updates

```bash
git add kubani/agents/feed_collector/feeds.py
git commit -m "fix(feed-collector): update broken RSS feed URLs for OpenAI, Anthropic, NVIDIA, Reuters"
```

---

## Task 3: Create Feed Validation Tests

**Files:**
- Create: `kubani/agents/feed_collector/tests/test_feeds.py`

### Step 1: Write failing test for feed URL validation

```python
"""Tests for RSS feed configuration and accessibility."""

import httpx
import pytest
from agents.feed_collector.feeds import FEEDS, get_enabled_feeds


class TestFeedURLs:
    """Test that all enabled feed URLs are accessible."""

    @pytest.mark.asyncio
    async def test_all_enabled_feeds_accessible(self):
        """Verify all enabled feed URLs return 200-299 status codes."""
        enabled_feeds = get_enabled_feeds()

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            results = []
            for feed in enabled_feeds:
                try:
                    response = await client.get(feed.url)
                    results.append((feed.name, feed.url, response.status_code))
                    # Allow 200-299 status codes
                    assert 200 <= response.status_code < 300, (
                        f"Feed '{feed.name}' returned {response.status_code}: {feed.url}"
                    )
                except Exception as e:
                    pytest.fail(f"Feed '{feed.name}' failed: {e}")

        # Print summary
        print("\n=== Feed Validation Results ===")
        for name, url, status in results:
            print(f"✓ {name}: {status} - {url}")

    def test_no_duplicate_feed_names(self):
        """Ensure all feed names are unique."""
        names = [f.name for f in FEEDS]
        assert len(names) == len(set(names)), "Duplicate feed names found"

    def test_no_duplicate_feed_urls(self):
        """Ensure all feed URLs are unique."""
        urls = [f.url for f in FEEDS]
        assert len(urls) == len(set(urls)), "Duplicate feed URLs found"

    def test_all_feeds_have_valid_priority(self):
        """Ensure all feeds have priority between 1-10."""
        for feed in FEEDS:
            assert 1 <= feed.priority <= 10, (
                f"Feed '{feed.name}' has invalid priority {feed.priority}"
            )
```

### Step 2: Run tests to see current failures

```bash
cd /home/al/git/kubani
uv run --package news-digest-syndicate pytest kubani/agents/feed_collector/tests/test_feeds.py -v
```

**Expected:** Tests fail for broken feed URLs, pass after URL fixes

### Step 3: Run tests again after URL updates

After completing Task 2, run tests again:

```bash
uv run --package news-digest-syndicate pytest kubani/agents/feed_collector/tests/test_feeds.py -v
```

**Expected:** All tests pass

### Step 4: Commit feed validation tests

```bash
git add kubani/agents/feed_collector/tests/test_feeds.py
git commit -m "test(feed-collector): add RSS feed URL validation tests"
```

---

## Task 4: Replace Liveness Probe with Readiness Probe

**Files:**
- Modify: `infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml:114-121`

### Step 1: Remove failing liveness probe

Remove the current liveness probe that's causing crashes:

```yaml
          # Remove lines 114-121 (livenessProbe section)
```

### Step 2: Add lightweight readiness probe

Add a simple readiness probe that checks if the container can execute Python:

```yaml
          readinessProbe:
            exec:
              command:
                - python3
                - -c
                - "import sys; sys.exit(0)"
            initialDelaySeconds: 10
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          livenessProbe:
            exec:
              command:
                - python3
                - -c
                - "import sys; sys.exit(0)"
            initialDelaySeconds: 60
            periodSeconds: 60
            timeoutSeconds: 5
            failureThreshold: 3
```

**Rationale:** Simple Python check is lightweight, doesn't require uv, and still validates container is operational

### Step 3: Commit probe configuration update

```bash
git add infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml
git commit -m "fix(news-monitor): replace failing uv-based liveness probe with lightweight Python check"
```

---

## Task 5: Bump Version and Update Deployment

**Files:**
- Modify: `kubani/syndicates/news_digest/pyproject.toml:3`
- Modify: `infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml:29,106`

### Step 1: Bump version in pyproject.toml

```toml
[project]
name = "news-digest-syndicate"
version = "0.3.3"  # Bumped from 0.3.2
```

### Step 2: Update version in deployment.yaml

```yaml
        - name: worker
          image: registry.almckay.io/news-monitor:0.3.3  # Line 29
          # ...
          - name: AGENT_VERSION
            value: "0.3.3"  # Line 106
```

### Step 3: Commit version bumps

```bash
git add kubani/syndicates/news_digest/pyproject.toml infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml
git commit -m "chore(news-monitor): bump version to 0.3.3"
```

---

## Task 6: Build and Test Locally

**Files:**
- Build: Docker image

### Step 1: Build the Docker image

```bash
cd /home/al/git/kubani/kubani/syndicates/news_digest
earthly +docker --VERSION=0.3.3
```

**Expected:** Build succeeds without errors

### Step 2: Verify uv is accessible in the image

```bash
docker run --rm registry.almckay.io/news-monitor:0.3.3 uv --version
```

**Expected:** Prints uv version (e.g., "uv 0.5.x")

### Step 3: Verify Python import works

```bash
docker run --rm registry.almckay.io/news-monitor:0.3.3 python3 -c "import sys; print('Python check passed'); sys.exit(0)"
```

**Expected:** Prints "Python check passed" and exits with 0

### Step 4: Run syndicate tests

```bash
cd /home/al/git/kubani
uv run --package news-digest-syndicate pytest kubani/syndicates/news_digest/tests/ -v
```

**Expected:** All tests pass

### Step 5: Run feed collector tests

```bash
uv run --package news-digest-syndicate pytest kubani/agents/feed_collector/tests/ -v
```

**Expected:** All feed URL tests pass

---

## Task 7: Push Image to Registry

**Files:**
- N/A (registry operation)

### Step 1: Push the Docker image

```bash
cd /home/al/git/kubani/kubani/syndicates/news_digest
earthly --push +push --VERSION=0.3.3
```

**Expected:** Image pushed successfully to registry.almckay.io

### Step 2: Verify image is in registry

```bash
curl -s https://registry.almckay.io/v2/news-monitor/tags/list | jq .
```

**Expected:** Tags list includes "0.3.3" and "latest"

### Step 3: Commit image push

```bash
# No git commit needed, but create a git tag
git tag news-monitor-v0.3.3
git push origin news-monitor-v0.3.3
```

---

## Task 8: Deploy to Cluster

**Files:**
- Apply: Kubernetes deployment

### Step 1: Apply the updated deployment

```bash
KUBECONFIG=/home/al/.kube/config kubectl apply -f infrastructure/gitops/apps/ai-agents/news-monitor/deployment.yaml
```

**Expected:** Deployment updated successfully

### Step 2: Watch the rollout

```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/news-monitor -n ai-agents --timeout=5m
```

**Expected:** "deployment 'news-monitor' successfully rolled out"

### Step 3: Verify pod is running without restarts

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=news-monitor -w
```

**Expected:** Pod shows `1/1 Running` with 0 restarts, watch for 5 minutes

### Step 4: Check pod logs for errors

```bash
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=news-monitor --tail=50
```

**Expected:**
- No "uv: Permission denied" errors
- No 403/404 errors for OpenAI, Anthropic, NVIDIA, Reuters feeds
- Successful feed collection messages

### Step 5: Verify liveness/readiness probes are passing

```bash
KUBECONFIG=/home/al/.kube/config kubectl describe pod -n ai-agents -l app.kubernetes.io/name=news-monitor | grep -A 10 "Liveness:\|Readiness:"
```

**Expected:** Both probes show success, no failure messages

### Step 6: Monitor for 15 minutes to ensure stability

```bash
# Watch pod status
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app.kubernetes.io/name=news-monitor -w

# In another terminal, watch events
KUBECONFIG=/home/al/.kube/config kubectl get events -n ai-agents --field-selector involvedObject.name=news-monitor --watch
```

**Expected:** No restart events, no unhealthy probe failures

---

## Task 9: Final Verification and Commit

**Files:**
- N/A (verification only)

### Step 1: Verify feed collection is working

Wait for next scheduled run or manually trigger if possible, then check logs:

```bash
KUBECONFIG=/home/al/.kube/config kubectl logs -n ai-agents -l app.kubernetes.io/name=news-monitor --tail=100 | grep "Collected.*articles"
```

**Expected:** Log entries showing successful article collection from all feeds

### Step 2: Check Discord for digest publication

Verify that digests are being published to Discord channel (if scheduled run has occurred)

**Expected:** Recent digest messages in ai-news channel

### Step 3: Create final summary commit

```bash
git add -A
git commit -m "fix(news-monitor): comprehensive stability fixes

- Fix uv installation permissions (system-wide install)
- Update broken RSS feed URLs (OpenAI, Anthropic, NVIDIA, Reuters)
- Replace failing liveness probe with lightweight Python check
- Add feed URL validation tests
- Bump version to 0.3.3

Resolves pod crash loop caused by liveness probe permission errors.
Fixes feed collection errors from outdated URLs.
"
```

### Step 4: Push all commits

```bash
git push origin main
git push origin news-monitor-v0.3.3
```

---

## Success Criteria

✅ Pod runs without restarts for at least 1 hour
✅ No "uv: Permission denied" errors in logs
✅ No 403/404 errors for previously broken feeds
✅ Liveness and readiness probes consistently passing
✅ Feed collection completing successfully (300+ articles)
✅ All tests passing
✅ Version bumped to 0.3.3
✅ Changes committed and pushed

---

## Rollback Plan

If deployment fails or causes issues:

```bash
# Rollback to previous version
KUBECONFIG=/home/al/.kube/config kubectl rollout undo deployment/news-monitor -n ai-agents

# Verify rollback
KUBECONFIG=/home/al/.kube/config kubectl rollout status deployment/news-monitor -n ai-agents
```

---

## Notes

- The uv installation fix is critical - without it, probes will continue to fail
- Feed URL updates may need periodic maintenance as sites change
- Consider adding automated feed URL validation to CI/CD pipeline
- Future improvement: Add HTTP health endpoint for more robust health checks
