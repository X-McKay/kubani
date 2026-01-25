# Research: Hot-Reload for Skills

**Status**: Deferred to Phase 8
**Date**: 2026-01-22
**Context**: Kubani Restructuring Phase 0

## Problem Statement

When skills are updated, the Skills MCP Server currently requires a restart to pick up changes. Hot-reload would allow skill updates to take effect immediately without service disruption.

## Current State (Deferred)

This research is deferred to Phase 8 (Polish & Enhancement). For Phase 1-7, we will use restart-based reload:

1. Update skill files in kubani/skills/
2. Restart Skills MCP Server pod
3. New skill versions are loaded

This is acceptable for initial implementation because:
- Skill updates are infrequent
- Pod restarts are fast (~5 seconds)
- No user-facing impact (agents retry on transient errors)

## Research Areas (Phase 8)

### 1. MCP Protocol Support

The MCP specification includes a `tools/list` endpoint that returns available tools. Key questions:
- Does MCP support tool refresh signals?
- Can servers notify clients of tool changes?
- How do clients cache tool lists?

### 2. Filesystem Watching

Options for detecting skill file changes:
- `watchdog` library for filesystem events
- `inotify` on Linux
- Periodic polling (simple but less efficient)

### 3. Graceful Reload

When reloading skills:
- In-flight skill executions should complete
- New requests should use new skill versions
- No requests should be dropped

Potential approaches:
- Two-phase reload (load new, then swap)
- Request draining before reload
- Versioned skill instances

### 4. MCP Client Notification

How to notify MCP clients of skill changes:
- Server-sent events (SSE) for push notification
- `tools/list_changed` notification in MCP spec
- Client-side polling with cache invalidation

## Implementation Sketch

```python
class SkillsMCPServer:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, Skill] = {}
        self._watcher = None

    async def start_hot_reload(self):
        """Start watching for skill file changes."""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class SkillChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path.endswith("SKILL.md"):
                    self._reload_skill(event.src_path)

        self._watcher = Observer()
        self._watcher.schedule(
            SkillChangeHandler(),
            str(self.skills_dir),
            recursive=True,
        )
        self._watcher.start()

    def _reload_skill(self, skill_path: str):
        """Reload a single skill."""
        skill_dir = Path(skill_path).parent
        skill_name = self._path_to_skill_name(skill_dir)

        new_skill = self._load_skill(skill_dir)
        self.skills[skill_name] = new_skill

        logger.info(f"Hot-reloaded skill: {skill_name}")
```

## Alternative: ConfigMap Reload

If skills are deployed via Kubernetes ConfigMap:
- Use ConfigMap watch for changes
- Kubernetes handles propagation
- Simpler than filesystem watching

## Success Criteria

Hot-reload implementation should:
1. Detect skill changes within 5 seconds
2. Not interrupt in-flight skill executions
3. Notify connected MCP clients of changes
4. Have zero downtime for skill updates

## References

- [MCP Specification - Tool Notifications](https://spec.modelcontextprotocol.io/)
- [Watchdog Library](https://python-watchdog.readthedocs.io/)
- [Kubernetes ConfigMap Watch](https://kubernetes.io/docs/concepts/configuration/configmap/)
