
># Nexus Implementation Plan: 04 - Autonomous OCI-Native Skill Management

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Overview

This document details the implementation of the autonomous, OCI-native skill management system. This system allows the Nexus agent to create, validate, and deploy its own skills in a secure and scalable manner, moving away from a manual, GitOps-based process.

This plan covers four key components:

1.  The **`Skill Synthesizer`** agent.
2.  The **OCI artifact** format for skills.
3.  The **`Skill Validation Workflow`**.
4.  The **`Skill Registry`** service.

## 2. Component: `Skill Synthesizer` Agent

-   **Type:** A specialized Strands agent, likely part of the existing `learning_system` syndicate.
-   **Purpose:** To receive a natural language request for a skill and generate the `SKILL.md` and any associated code.
-   **Workflow:**
    1.  Receives a task from the main Nexus Syndicate (e.g., "Create a skill to format text as a table").
    2.  Uses an LLM to write the `SKILL.md` file, defining the skill's name, description, inputs, and outputs.
    3.  If the skill requires code, it writes the code to a separate file (e.g., `main.py`).
    4.  Packages the generated files into a standardized OCI artifact.
    5.  Pushes the artifact to the OCI registry.

## 3. Component: Skill OCI Artifact

-   **Format:** A standard OCI image artifact, built using a tool like `oras` or a simple Dockerfile.
-   **Registry:** The existing Harbor registry in the `kubani` cluster.
-   **Structure:** The artifact will contain the skill's files in a simple, flat structure:
    -   `/SKILL.md`
    -   `/main.py` (if applicable)
    -   `/helper.py` (if applicable)
-   **Tagging:** Artifacts will be tagged with a semantic version, e.g., `registry.kubani.local/skills/text/formatter:1.0.0`.

## 4. Component: `Skill Validation Workflow`

This is a Temporal workflow that is automatically triggered when a new skill artifact is pushed to the registry (e.g., via a registry webhook).

-   **Name:** `SkillValidationWorkflow`
-   **Task Queue:** `skill-validation`
-   **Arguments:**
    -   `oci_url: str`: The URL of the newly pushed skill artifact.

**Stages:**

1.  **Static Analysis Activity:**
    -   Pulls the artifact and scans the `SKILL.md` for policy violations (e.g., requesting dangerous tools).
    -   Scans any Python code using `bandit` or a similar static analysis tool to find common security vulnerabilities.

2.  **Sandbox Execution Activity:**
    -   Runs the skill in the ephemeral sandbox (as defined in Plan 03) with a set of test inputs.
    -   Monitors its behavior, logging all file access, network connections, and subprocess calls.

3.  **LLM Peer Review Activity:**
    -   Sends the skill's code and a summary of its behavior to a specialized "auditor" LLM.
    -   Asks the LLM to identify potential security risks, logical flaws, or deviations from the skill's stated purpose.

4.  **Risk Scoring and Approval Activity:**
    -   Aggregates the results from all previous stages.
    -   Calculates a final risk score based on a weighted formula.
    -   Compares the score to the Approval Policy:
        -   If low-risk, automatically approve.
        -   If medium-risk, signal a separate `HumanApprovalWorkflow` and wait for a user to approve or deny it via the UI.
        -   If high-risk, automatically reject.

5.  **Registration Activity:**
    -   If the skill is approved, this activity calls the `Skill Registry` API to register the new, validated skill.

## 5. Component: `Skill Registry` Service

-   **Technology:** FastAPI with a PostgreSQL database.
-   **Purpose:** To be the central, authoritative source of truth for all validated, available skills.

**API Endpoints:**

-   `POST /register`: Called by the `Registration Activity` to add a new skill to the registry. Requires authentication to ensure only the validation workflow can call it.
-   `GET /skills`: Lists all available skills. Can be filtered by name, category, etc.
-   `GET /skills/{name}/{version}`: Retrieves the detailed metadata for a specific version of a skill, including its OCI URL and risk profile.

**Database Schema (PostgreSQL):**

```sql
CREATE TABLE skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    oci_url VARCHAR(1024) NOT NULL,
    description TEXT,
    risk_score FLOAT,
    status VARCHAR(50) NOT NULL, -- e.g., 'validated', 'pending_approval', 'rejected'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name, version)
);
```

This OCI-native system provides a robust, secure, and highly automated foundation for the agent's self-improvement, allowing it to evolve its capabilities safely over time.
