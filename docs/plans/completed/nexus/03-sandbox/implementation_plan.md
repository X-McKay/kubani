
># Nexus Implementation Plan: 03 - Ephemeral Execution Sandbox

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Overview

This document details the implementation of the secure execution sandbox for Kubani Nexus. As per the architectural decision, we will implement an **ephemeral sandbox per execution**. This means every time a skill is run, it occurs within a new, short-lived, and heavily restricted container, providing the highest possible level of security and isolation.

This component is the cornerstone of the agent's safety, preventing skills from interfering with each other or the underlying host system.

## 2. Technology Stack

-   **Containerization:** Docker
-   **Orchestration:** The sandbox will be managed by a Temporal Activity (`execute_skill_activity`), which will interact with the Docker daemon on the host.
-   **Base Image:** A minimal, hardened Debian-based Docker image.

## 3. Sandbox Design

### 3.1. The `execute_skill_activity`

This Temporal activity is the entry point for all skill execution. It will be responsible for the entire lifecycle of the sandbox.

**Arguments:**

-   `skill_oci_url: str`: The URL of the skill's OCI artifact in the registry.
-   `skill_input: Dict[str, Any]`: The input data for the skill.

**Logic:**

1.  **Pull Artifact:** Pull the skill's OCI artifact from the registry.
2.  **Create Sandbox Container:** Create and start a new Docker container based on the hardened base image. The container will be configured with strict security constraints.
3.  **Inject Skill & Input:** Copy the skill's `SKILL.md` and any other files from the OCI artifact into the container's workspace. Write the `skill_input` to a predefined file (e.g., `/workspace/input.json`).
4.  **Execute:** Run the skill's entrypoint command inside the container.
5.  **Capture Output:** Capture the `stdout`, `stderr`, and the final exit code from the container.
6.  **Cleanup:** **Always** stop and remove the container, even if the execution failed.
7.  **Return Result:** Return the captured output to the parent workflow.

### 3.2. Security Constraints

The sandbox container will be created with the following security settings to enforce the principle of least privilege:

-   **No Network Access by Default:** The container will be created with `--network=none`. Skills that explicitly require network access (e.g., a `web_search` skill) will have this requirement declared in their `SKILL.md`. The `execute_skill_activity` will parse this and only enable limited network access for those specific skills.
-   **Read-Only Root Filesystem:** The container's root filesystem will be mounted as read-only (`--read-only`).
-   **Ephemeral Workspace:** A dedicated, ephemeral volume will be mounted at `/workspace`. This is the only location where the skill will have write access.
-   **Resource Limits:** Strict CPU and memory limits will be applied (`--cpus`, `--memory`) to prevent resource exhaustion attacks.
-   **No Privileges:** The container will run with `--cap-drop=ALL` and `--security-opt=no-new-privileges` to prevent any form of privilege escalation.
-   **AST-based Shell Guard:** Before executing any shell command within the container, the command will be parsed using an Abstract Syntax Tree (AST) parser. This will allow us to detect and block dangerous constructs like command substitution (`$(...)`), backticks (`` `...` ``), and shell redirection (`>`), providing a much more robust defense than simple string matching.

### 3.3. Base Image

We will create a new `nexus-sandbox-base` Docker image. This image will contain:

-   A minimal Debian or Alpine base.
-   A non-root user that the skill will run as.
-   The necessary runtimes for executing skills (e.g., a minimal Python installation).
-   The AST shell parsing utility.

This image will be kept as small as possible to minimize attack surface and reduce container startup time.

## 4. Interaction with the Skill Registry

The `execute_skill_activity` will need to communicate with the `Skill Registry` service (detailed in Plan 04) to resolve the `skill_oci_url` and retrieve the skill's metadata, including its security requirements (e.g., whether it needs network access).

This ensures that the sandbox is configured with the precise level of privilege required for that specific skill, and no more.
