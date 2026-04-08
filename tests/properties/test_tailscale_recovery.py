"""Property-based tests for Tailscale-to-K3s recovery systemd drop-in.

Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes
Validates: Requirements 1.5, 10.1
"""

from pathlib import Path

CONTROL_PLANE_DROP_IN = Path(
    "infrastructure/ansible/roles/k3s_control_plane/files/tailscale-recovery.conf"
)
WORKER_DROP_IN = Path(
    "infrastructure/ansible/roles/k3s_worker/files/tailscale-recovery.conf"
)

CONTROL_PLANE_TASK_FILE = Path(
    "infrastructure/ansible/roles/k3s_control_plane/tasks/tailscale_recovery.yml"
)
WORKER_TASK_FILE = Path(
    "infrastructure/ansible/roles/k3s_worker/tasks/tailscale_recovery.yml"
)

CONTROL_PLANE_MAIN = Path(
    "infrastructure/ansible/roles/k3s_control_plane/tasks/main.yml"
)
WORKER_MAIN = Path(
    "infrastructure/ansible/roles/k3s_worker/tasks/main.yml"
)

REQUIRED_DIRECTIVES = [
    "BindsTo=tailscaled.service",
    "After=tailscaled.service",
]


def test_property_7_control_plane_drop_in_file_exists():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The drop-in file for the control plane role must exist at the expected path.

    Validates: Requirements 1.5, 10.1
    """
    assert CONTROL_PLANE_DROP_IN.exists(), (
        f"Control plane drop-in file not found at {CONTROL_PLANE_DROP_IN}. "
        "This file must exist so Ansible can install it during provisioning."
    )


def test_property_7_worker_drop_in_file_exists():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The drop-in file for the worker role must exist at the expected path.

    Validates: Requirements 1.5, 10.1
    """
    assert WORKER_DROP_IN.exists(), (
        f"Worker drop-in file not found at {WORKER_DROP_IN}. "
        "This file must exist so Ansible can install it during provisioning."
    )


def test_property_7_control_plane_drop_in_has_binds_to():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The control plane drop-in must contain BindsTo=tailscaled.service so that K3s
    stops and restarts when Tailscale does.

    Validates: Requirements 1.1, 1.5, 10.1
    """
    content = CONTROL_PLANE_DROP_IN.read_text()
    for directive in REQUIRED_DIRECTIVES:
        assert directive in content, (
            f"Control plane drop-in is missing required directive '{directive}'. "
            f"File content:\n{content}"
        )


def test_property_7_worker_drop_in_has_binds_to():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The worker drop-in must contain BindsTo=tailscaled.service so that K3s-agent
    stops and restarts when Tailscale does.

    Validates: Requirements 1.1, 1.5, 10.1
    """
    content = WORKER_DROP_IN.read_text()
    for directive in REQUIRED_DIRECTIVES:
        assert directive in content, (
            f"Worker drop-in is missing required directive '{directive}'. "
            f"File content:\n{content}"
        )


def test_property_7_drop_in_files_are_identical():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    Both drop-in files (control plane and worker) must have identical content,
    since the recovery behaviour is the same for both node types.

    Validates: Requirements 1.5, 10.1
    """
    cp_content = CONTROL_PLANE_DROP_IN.read_text()
    worker_content = WORKER_DROP_IN.read_text()
    assert cp_content == worker_content, (
        "Control plane and worker drop-in files must have identical content.\n"
        f"Control plane:\n{cp_content}\nWorker:\n{worker_content}"
    )


def test_property_7_control_plane_task_installs_drop_in():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The control plane Ansible task file must install the drop-in to the correct
    systemd directory: /etc/systemd/system/k3s.service.d/

    Validates: Requirements 1.5, 10.1
    """
    assert CONTROL_PLANE_TASK_FILE.exists(), (
        f"Control plane tailscale_recovery task file not found at {CONTROL_PLANE_TASK_FILE}"
    )
    content = CONTROL_PLANE_TASK_FILE.read_text()
    assert "k3s.service.d" in content, (
        "Control plane task must install drop-in to /etc/systemd/system/k3s.service.d/"
    )
    assert "tailscale-recovery.conf" in content, (
        "Control plane task must reference tailscale-recovery.conf"
    )


def test_property_7_worker_task_installs_drop_in():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The worker Ansible task file must install the drop-in to the correct
    systemd directory: /etc/systemd/system/k3s-agent.service.d/

    Validates: Requirements 1.5, 10.1
    """
    assert WORKER_TASK_FILE.exists(), (
        f"Worker tailscale_recovery task file not found at {WORKER_TASK_FILE}"
    )
    content = WORKER_TASK_FILE.read_text()
    assert "k3s-agent.service.d" in content, (
        "Worker task must install drop-in to /etc/systemd/system/k3s-agent.service.d/"
    )
    assert "tailscale-recovery.conf" in content, (
        "Worker task must reference tailscale-recovery.conf"
    )


def test_property_7_control_plane_main_includes_recovery_task():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The control plane role's main.yml must include the tailscale_recovery.yml task file
    so the drop-in is installed during every provisioning run.

    Validates: Requirements 1.5, 10.1
    """
    content = CONTROL_PLANE_MAIN.read_text()
    assert "tailscale_recovery.yml" in content, (
        "k3s_control_plane/tasks/main.yml must include tailscale_recovery.yml"
    )


def test_property_7_worker_main_includes_recovery_task():
    """
    Feature: cluster-stability, Property 7: Systemd drop-in is installed on all provisioned nodes

    The worker role's main.yml must include the tailscale_recovery.yml task file
    so the drop-in is installed during every provisioning run.

    Validates: Requirements 1.5, 10.1
    """
    content = WORKER_MAIN.read_text()
    assert "tailscale_recovery.yml" in content, (
        "k3s_worker/tasks/main.yml must include tailscale_recovery.yml"
    )
