# Enhanced K8s-Monitor Architecture Design

## Overview

This document outlines the enhanced architecture for the k8s-monitor agent, implementing intelligent health check monitoring with automated investigation, remediation, and learning capabilities.

## Design Goals

1. **Proactive Health Monitoring**: Periodic health checks with appropriate notifications
2. **Intelligent Remediation**: Automated investigation and fix attempts with transparency
3. **Learning System**: Memory integration for pattern recognition and continuous improvement
4. **User Experience**: Clean, informative Discord notifications with appropriate detail levels
5. **Robustness**: Comprehensive testing and error handling
6. **Reusability**: Keep core agents generic for use across multiple workflows

## Architecture Components

### 1. Enhanced Health Check Workflow

**Current State:**
- Only posts to Discord when issues are detected
- No automatic remediation trigger

**Enhanced State:**
- Posts brief confirmation when cluster is healthy
- Triggers remediation workflow when issues are detected
- Integrates with memory system for pattern recognition

**Flow:**
```
ScheduledHealthCheckWorkflow (runs every N hours)
    ↓
ClusterHealthCheckWorkflow
    ↓
collect_and_analyze_cluster (swarm-based analysis)
    ↓
Decision Point: Healthy vs Issues
    ↓                           ↓
Healthy Path                Issues Path
    ↓                           ↓
post_brief_health_ok        post_issue_detected
                                ↓
                        IssueRemediationWorkflow (for each issue)
                                ↓
                        investigate → fix → verify → learn
                                ↓
                        post_remediation_updates (transparency)
```

### 2. Remediation Workflow Enhancement

**Current State:**
- Exists but not integrated with health check
- Basic investigation and fix attempts

**Enhanced State:**
- Automatically triggered by health check when issues detected
- Up to 3 retry attempts with investigation between each
- Full transparency via Discord at each stage
- Memory integration for learning

**Stages:**
1. **Issue Detection**: Post to Discord with issue details
2. **Investigation**: 
   - Check memory for similar past issues
   - Investigate using K8s tools (logs, events, describe)
   - Identify root cause
   - Post investigation results to Discord
3. **Remediation Planning**:
   - Determine fix strategy
   - Post planned remediation to Discord
4. **Fix Attempt**:
   - Execute remediation
   - Verify outcome
   - Post results to Discord
5. **Retry Logic** (if failed):
   - Re-investigate with new context
   - Try alternative approach
   - Post retry attempt to Discord
   - Repeat up to 3 times
6. **Learning**:
   - Store successful remediation in memory
   - Store failure patterns
   - Update recurrence tracking
7. **Escalation** (if all attempts fail):
   - Post escalation to Discord with full context
   - Include all attempts and findings

### 3. Discord Notification Enhancement

**Message Types:**

1. **Health Confirmation** (Healthy status):
   ```
   ✅ Cluster Health Check - All Systems Operational
   
   All nodes, pods, and deployments are healthy.
   Last checked: 2024-01-15 10:00:00 UTC
   ```

2. **Issue Detection**:
   ```
   🚨 Issue Detected: Pod CrashLoopBackOff
   
   Resource: Pod/app-backend
   Namespace: production
   Severity: Critical
   
   Starting automated investigation...
   ```

3. **Investigation Results**:
   ```
   🔍 Investigation Complete: Pod CrashLoopBackOff
   
   Root Cause: OOMKilled - container exceeded memory limit
   
   Evidence:
   - Last exit code: 137 (OOM)
   - Memory limit: 512Mi
   - Memory usage: 580Mi peak
   
   Similar Issues: Found 2 past occurrences (last: 3 days ago)
   
   Planned Remediation: Increase memory limit to 1Gi
   ```

4. **Fix Attempt**:
   ```
   🔧 Applying Fix (Attempt 1/3)
   
   Action: Updating deployment memory limit
   Command: kubectl patch deployment app-backend -p '{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"limits":{"memory":"1Gi"}}}]}}}}'
   
   Executing...
   ```

5. **Fix Success**:
   ```
   ✅ Issue Resolved: Pod CrashLoopBackOff
   
   Fix Applied: Increased memory limit to 1Gi
   Result: Pod now running successfully
   
   This issue has occurred 3 times. Consider:
   - Investigating memory leak in application
   - Setting permanent memory limit in deployment manifest
   
   Learning stored for future reference.
   ```

6. **Fix Failure & Retry**:
   ```
   ⚠️ Fix Attempt 1 Failed
   
   Result: Deployment updated but pod still crashing
   
   Re-investigating with new context...
   Attempt 2/3 starting...
   ```

7. **Escalation**:
   ```
   🚨 URGENT: Automated Remediation Failed
   
   Issue: Pod CrashLoopBackOff (app-backend)
   Attempts: 3/3 failed
   
   What was tried:
   1. Increased memory limit → Pod still crashing
   2. Rolled back to previous version → Image pull failed
   3. Restarted with debug mode → Container won't start
   
   Root Cause: Likely configuration issue in new deployment
   
   Action Required: Manual investigation needed
   - Check application logs
   - Verify configuration changes
   - Consider rollback to known good state
   ```

**Formatting Guidelines:**
- Use emoji for visual status indicators
- Keep titles concise and descriptive
- Provide appropriate detail level for each stage
- Use code blocks for commands and technical details
- Include actionable recommendations
- Show progression through remediation attempts

### 4. Memory System Enhancement

**Current State:**
- Basic memory storage via RemediationMemoryAgent
- Limited pattern recognition

**Enhanced State:**
- Track issue recurrence patterns
- Store successful remediation strategies
- Identify trends over time
- Provide context-aware recommendations

**Memory Schema:**
```python
{
    "issue_signature": "pod_crashloop_oom_app-backend",
    "occurrences": [
        {
            "timestamp": "2024-01-15T10:00:00Z",
            "root_cause": "OOMKilled - memory limit too low",
            "fix_applied": "Increased memory limit to 1Gi",
            "success": true,
            "time_to_resolution": "5m"
        }
    ],
    "recurrence_count": 3,
    "successful_fixes": ["increase_memory_limit"],
    "failed_fixes": [],
    "recommendations": [
        "Consider permanent fix: update base deployment manifest",
        "Investigate memory leak in application code"
    ],
    "pattern": "recurring_every_3_days"
}
```

**Memory Operations:**
- `search_similar_issues()`: Find past similar issues
- `store_remediation()`: Store successful/failed attempts
- `get_recurrence_count()`: Track how many times issue occurred
- `get_recommended_fix()`: Get best fix based on history
- `identify_patterns()`: Detect recurring patterns

### 5. Core Agent Improvements

**DiscordAgent (core/discord_agent.py):**
- Already generic and reusable ✓
- Enhance with richer formatting utilities
- Add support for multi-stage updates (threads or follow-ups)

**MemoryAgent (core/memory_agent.py):**
- Already generic and reusable ✓
- Enhance with pattern recognition prompts
- Add recurrence tracking logic

**Enhancements Needed:**
1. Add `discord_utils.py` with formatting helpers:
   - `format_issue_detection()`
   - `format_investigation_results()`
   - `format_fix_attempt()`
   - `format_escalation()`
   - `format_health_confirmation()`

2. Keep these utilities generic enough for reuse

### 6. Testing Strategy

**Unit Tests:**
- All activities (health check, investigation, remediation)
- All workflows (health check, remediation, retry logic)
- Discord formatting utilities
- Memory operations
- Status parsing and issue extraction

**Integration Tests:**
- End-to-end health check flow
- End-to-end remediation flow with retries
- Memory persistence and retrieval
- Discord notification delivery

**Mock Strategy:**
- Mock Kubernetes API calls
- Mock LLM responses (or use Ollama for local testing)
- Mock Discord webhook
- Mock Temporal workflow execution

**Test Coverage Goals:**
- Core logic: 90%+
- Activities: 85%+
- Workflows: 80%+
- Utilities: 95%+

## Implementation Plan

### Phase 1: Core Agent Improvements
- Enhance discord_utils with rich formatting functions
- Keep functions generic and reusable
- Add comprehensive docstrings

### Phase 2: Health Check Enhancement
- Modify ClusterHealthCheckWorkflow to always post to Discord
- Add brief confirmation for healthy status
- Trigger remediation workflow for detected issues

### Phase 3: Remediation Workflow Enhancement
- Integrate with health check workflow
- Add retry logic with re-investigation
- Add transparency via Discord at each stage
- Integrate memory lookup before investigation

### Phase 4: Memory Integration
- Enhance memory storage with pattern tracking
- Add recurrence counting
- Implement pattern recognition
- Store learnings after each remediation

### Phase 5: Discord Notification Enhancement
- Implement rich formatting for all message types
- Ensure appropriate detail levels
- Add visual indicators (emoji, colors)
- Test message rendering

### Phase 6: Comprehensive Testing
- Write unit tests for all new functionality
- Write integration tests for workflows
- Mock LLM calls for testing
- Achieve target coverage

### Phase 7: Validation
- Run full test suite
- Verify no breaking changes
- Test end-to-end flows
- Validate Discord message formatting

## Success Criteria

1. ✅ Health check posts brief confirmation when healthy
2. ✅ Health check triggers remediation when issues detected
3. ✅ Remediation workflow investigates issues thoroughly
4. ✅ Remediation workflow attempts fixes with up to 3 retries
5. ✅ Full transparency via Discord at each stage
6. ✅ Memory system tracks patterns and recurrence
7. ✅ Discord notifications are clean, informative, and well-formatted
8. ✅ Core agents remain generic and reusable
9. ✅ Comprehensive test coverage (85%+)
10. ✅ No breaking changes to existing functionality

## Technical Considerations

### Temporal Workflow Constraints
- Workflows must be deterministic
- Use `workflow.execute_activity()` for external calls
- Use `workflow.execute_child_workflow()` for sub-workflows
- Activities can be retried, workflows cannot

### Strands Swarm Patterns
- Entry point is ClusterTriageAgent
- Agents hand off to specialists as needed
- Swarm manages agent coordination
- Keep individual agent prompts focused

### Discord API Limits
- Rate limits: 5 requests per 2 seconds per webhook
- Message size: 2000 characters (use embeds for more)
- Embed description: 4096 characters
- Consider batching updates if needed

### Memory Persistence
- Currently using in-memory storage (RemediationMemoryAgent)
- Consider adding persistent storage (Redis, PostgreSQL) for production
- Ensure memory operations are fast (< 1s)

### LLM Inference
- Using vLLM for local inference
- Consider timeout and retry logic
- Mock for testing to avoid dependency

## Open Questions

1. Should we persist memory to a database or keep in-memory?
   - **Decision**: Start with in-memory, add persistence later if needed

2. Should we support Discord threads for multi-stage updates?
   - **Decision**: Use separate messages for now, add threading later if needed

3. Should we add a "dry-run" mode for remediation?
   - **Decision**: Yes, add a configuration flag for safety

4. Should we add metrics/observability beyond Discord?
   - **Decision**: Out of scope for this iteration, but design with extensibility in mind

## Next Steps

1. Implement core agent improvements (discord_utils)
2. Enhance health check workflow
3. Enhance remediation workflow
4. Integrate memory system
5. Write comprehensive tests
6. Validate and deliver
