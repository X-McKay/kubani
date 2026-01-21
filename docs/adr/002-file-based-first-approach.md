# ADR 002: File-Based First Approach

**Date:** 2026-01-20

**Status:** Accepted

## Context

We need to decide whether to build the skill development workflow with a database-first or file-based-first approach. A database provides centralized storage and querying, while a file-based system is simpler for local development.

## Decision

We will start with a **file-based system** and integrate the database in a later phase. The initial implementation will rely on the filesystem for:

- Skill storage and versioning
- Evaluation results
- Local history viewing

## Rationale

### Considered Options

1. **File-Based First (Chosen)**
   - **Pros:** Faster initial development, works offline, simpler for local development, easy to version control, database can be added later without breaking the workflow.
   - **Cons:** No centralized querying, history is limited to local files, harder to track trends.

2. **Database-First**
   - **Pros:** Centralized storage, rich querying, better for analytics, enables cluster-wide features from day one.
   - **Cons:** Slower initial development, requires database setup for local development, more complex workflow, harder to version control skill definitions.

### Justification

A file-based-first approach allows us to deliver a functional and valuable MVP much faster. It prioritizes the local developer experience, which is crucial for rapid iteration. The system is designed to be extended with database integration, so we are not sacrificing long-term capabilities.

## Consequences

- The initial implementation will not have centralized skill discovery or evaluation history.
- Cluster-based features will be limited until the database is integrated.
- Developers can work on skills offline without needing a database connection.
- All skill definitions and evaluation results can be version-controlled in Git.
