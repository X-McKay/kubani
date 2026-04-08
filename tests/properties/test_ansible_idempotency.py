"""Property-based tests for Ansible provisioning idempotency.

Feature: cluster-stability, Property 10: Ansible provisioning is idempotent
Validates: Requirements 10.5

Idempotency is verified by static analysis of the Ansible task files:
- Tasks that use `command` or `shell` must NOT have `changed_when: true`
  (hardcoding changed=true means every run reports a change, breaking idempotency)
- Tasks that install files must use the `copy` or `template` module
  (these are inherently idempotent — they only change when content differs)
- Tasks that install software must use `creates:` or `when: ... not installed` guards
- The `assert` module is always idempotent (read-only check)
- The `file` module (directory creation) is always idempotent
- The `systemd` module is always idempotent
"""

from pathlib import Path

import yaml

CONTROL_PLANE_TASKS = Path("infrastructure/ansible/roles/k3s_control_plane/tasks")
WORKER_TASKS = Path("infrastructure/ansible/roles/k3s_worker/tasks")

# Task files to inspect for idempotency
TASK_FILES = [
    CONTROL_PLANE_TASKS / "configure.yml",
    CONTROL_PLANE_TASKS / "install.yml",
    CONTROL_PLANE_TASKS / "tailscale_recovery.yml",
    WORKER_TASKS / "configure.yml",
    WORKER_TASKS / "install.yml",
    WORKER_TASKS / "tailscale_recovery.yml",
    WORKER_TASKS / "labels_taints.yml",
]

# Modules that are inherently idempotent — no further checks needed
INHERENTLY_IDEMPOTENT_MODULES = {
    "ansible.builtin.file",
    "ansible.builtin.copy",
    "ansible.builtin.template",
    "ansible.builtin.assert",
    "ansible.builtin.stat",
    "ansible.builtin.set_fact",
    "ansible.builtin.debug",
    "ansible.builtin.wait_for",
    "ansible.builtin.pause",
    "ansible.builtin.uri",
    "ansible.builtin.include_tasks",
    "ansible.builtin.systemd",
    "ansible.builtin.get_url",
}

# Modules that require explicit idempotency guards
REQUIRES_GUARD_MODULES = {
    "ansible.builtin.command",
    "ansible.builtin.shell",
}


def load_tasks(path: Path) -> list[dict]:
    """Load and return the list of tasks from a YAML task file."""
    assert path.exists(), f"Task file not found: {path}"
    with open(path) as f:
        content = yaml.safe_load(f)
    assert isinstance(content, list), f"Expected a list of tasks in {path}, got {type(content)}"
    return content


def get_module_name(task: dict) -> str | None:
    """Return the Ansible module name used by a task, or None if not identifiable."""
    for key in task:
        if key.startswith("ansible.builtin.") or key in {
            "command", "shell", "copy", "template", "file", "assert",
            "stat", "set_fact", "debug", "wait_for", "pause", "uri",
            "include_tasks", "systemd", "get_url",
        }:
            # Normalise short names to FQCN
            if not key.startswith("ansible.builtin."):
                return f"ansible.builtin.{key}"
            return key
    return None


def task_has_changed_when_true(task: dict) -> bool:
    """Return True if the task unconditionally sets changed_when: true."""
    changed_when = task.get("changed_when")
    if changed_when is True:
        return True
    if isinstance(changed_when, str) and changed_when.strip().lower() == "true":
        return True
    return False


def task_has_creates_guard(task: dict) -> bool:
    """Return True if the task uses args.creates to skip when already done."""
    args = task.get("args", {})
    return "creates" in args


def task_has_when_guard(task: dict) -> bool:
    """Return True if the task has a `when:` condition (any guard is acceptable)."""
    return "when" in task


def task_has_changed_when_conditional(task: dict) -> bool:
    """Return True if the task has a non-trivial changed_when expression."""
    changed_when = task.get("changed_when")
    if changed_when is None:
        return False
    if changed_when is True:
        return False  # unconditional — not a conditional
    if isinstance(changed_when, str) and changed_when.strip().lower() == "true":
        return False
    return True  # any other value is a conditional expression


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_property_10_all_task_files_exist():
    """
    Feature: cluster-stability, Property 10: Ansible provisioning is idempotent

    All expected task files must exist so idempotency can be verified.

    Validates: Requirements 10.5
    """
    for task_file in TASK_FILES:
        assert task_file.exists(), (
            f"Expected task file not found: {task_file}. "
            "All role task files must exist for idempotency verification."
        )


def test_property_10_command_tasks_do_not_hardcode_changed_when_true():
    """
    Feature: cluster-stability, Property 10: Ansible provisioning is idempotent

    For any task using the `command` or `shell` module, `changed_when: true` must
    NOT be used. Hardcoding changed=true means every playbook run reports a change,
    which breaks idempotency — a second run would always appear to make changes.

    Acceptable alternatives:
    - `changed_when: false` (task never changes state, e.g. read-only commands)
    - `changed_when: <expression>` (conditional based on command output)
    - `creates:` argument (skip if file already exists)
    - `when:` guard (skip if condition already met)

    Validates: Requirements 10.5
    """
    violations = []

    for task_file in TASK_FILES:
        tasks = load_tasks(task_file)
        for task in tasks:
            module = get_module_name(task)
            if module not in REQUIRES_GUARD_MODULES:
                continue

            task_name = task.get("name", "<unnamed>")

            if task_has_changed_when_true(task):
                violations.append(
                    f"{task_file.name}: task '{task_name}' uses {module} with "
                    f"`changed_when: true`. Use a conditional expression or `creates:` instead."
                )

    assert not violations, (
        "The following tasks hardcode `changed_when: true`, breaking idempotency:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_property_10_command_tasks_have_idempotency_mechanism():
    """
    Feature: cluster-stability, Property 10: Ansible provisioning is idempotent

    For any task using `command` or `shell`, at least one idempotency mechanism
    must be present:
    - `changed_when: false` or a conditional expression
    - `creates:` argument
    - `when:` guard

    Validates: Requirements 10.5
    """
    violations = []

    for task_file in TASK_FILES:
        tasks = load_tasks(task_file)
        for task in tasks:
            module = get_module_name(task)
            if module not in REQUIRES_GUARD_MODULES:
                continue

            task_name = task.get("name", "<unnamed>")

            has_mechanism = (
                task_has_creates_guard(task)
                or task_has_when_guard(task)
                or task_has_changed_when_conditional(task)
                or task.get("changed_when") is False
                or task.get("changed_when") == "false"
            )

            if not has_mechanism:
                violations.append(
                    f"{task_file.name}: task '{task_name}' uses {module} without any "
                    "idempotency mechanism (no `creates:`, `when:`, or `changed_when`)."
                )

    assert not violations, (
        "The following command/shell tasks lack an idempotency mechanism:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_property_10_file_installation_uses_idempotent_modules():
    """
    Feature: cluster-stability, Property 10: Ansible provisioning is idempotent

    Tasks that install configuration files (drop-ins, config files) must use
    `copy` or `template` modules, which are inherently idempotent — they only
    write when the destination content differs from the source.

    Validates: Requirements 10.5
    """
    # Verify the tailscale recovery drop-in installation uses `copy`
    for task_file in [
        CONTROL_PLANE_TASKS / "tailscale_recovery.yml",
        WORKER_TASKS / "tailscale_recovery.yml",
    ]:
        tasks = load_tasks(task_file)
        install_tasks = [
            t for t in tasks
            if "tailscale-recovery.conf" in str(t.get("ansible.builtin.copy", ""))
            or (
                get_module_name(t) in {"ansible.builtin.copy", "ansible.builtin.template"}
                and "tailscale-recovery.conf" in str(t)
            )
        ]
        assert len(install_tasks) >= 1, (
            f"{task_file.name}: expected at least one task installing tailscale-recovery.conf "
            "using the `copy` or `template` module."
        )
        for task in install_tasks:
            module = get_module_name(task)
            assert module in {"ansible.builtin.copy", "ansible.builtin.template"}, (
                f"{task_file.name}: tailscale-recovery.conf installation task uses "
                f"'{module}' instead of `copy` or `template`. "
                "Only `copy` and `template` are inherently idempotent for file installation."
            )


def test_property_10_install_tasks_use_version_check_guard():
    """
    Feature: cluster-stability, Property 10: Ansible provisioning is idempotent

    K3s installation tasks must check whether K3s is already installed at the
    correct version before running the installer script. This prevents re-running
    the installer on every playbook execution.

    Validates: Requirements 10.5
    """
    for task_file in [
        CONTROL_PLANE_TASKS / "install.yml",
        WORKER_TASKS / "install.yml",
    ]:
        tasks = load_tasks(task_file)
        task_names = [t.get("name", "") for t in tasks]

        # Must have a stat check for the k3s binary
        has_stat_check = any(
            get_module_name(t) == "ansible.builtin.stat" for t in tasks
        )
        assert has_stat_check, (
            f"{task_file.name}: must include a `stat` task to check if K3s binary exists "
            "before attempting installation."
        )

        # Must set a fact to gate installation
        has_set_fact = any(
            get_module_name(t) == "ansible.builtin.set_fact" for t in tasks
        )
        assert has_set_fact, (
            f"{task_file.name}: must use `set_fact` to record whether installation is needed, "
            "so subsequent tasks can be gated with `when: k3s_install_needed`."
        )

        # The shell/command that runs the installer must have a `when:` guard
        installer_tasks = [
            t for t in tasks
            if get_module_name(t) in REQUIRES_GUARD_MODULES
            and "install.sh" in str(t)
        ]
        for installer_task in installer_tasks:
            assert task_has_when_guard(installer_task), (
                f"{task_file.name}: installer task '{installer_task.get('name', '<unnamed>')}' "
                "must have a `when:` guard to prevent re-running on already-provisioned nodes."
            )
