# TODO

Outstanding items and future improvements.

## News Monitor

### Trends Section
- [ ] Revisit the trends section in ExecutiveBrief format
  - Current implementation shows basic momentum indicators (↑ ↓ →)
  - Consider adding more context/analysis for each trend
  - May want to deduplicate similar trends
  - Evaluate if trends granular message provides enough value

### Company News Deduplication
- [ ] Add deduplication logic for company news
  - Same story appears multiple times from different sources
  - Should consolidate into single entry with source attribution

## Registry API

### Skills API URL Encoding
- [ ] Fix GET `/api/v1/skills/{id}` to handle URL-encoded IDs
  - Skill IDs contain slashes (e.g., `general/memory/search-memory`)
  - GET returns 404 for URL-encoded IDs like `general%2Fmemory%2Fsearch-memory`
  - Causes sync to show "created" every run instead of "unchanged"
  - Options: decode the path parameter, or use query param instead

### MCP Policies Deduplication
- [ ] Add deduplication check for MCP policies
  - Currently creates new policy records on every sync
  - Should check if policy with same (agent_pattern, server_id) exists
  - Either return existing or implement upsert behavior
