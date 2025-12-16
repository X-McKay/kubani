"""Tests for Kubernetes inspection tools."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestGetNodeStatus:
    """Tests for get_node_status tool."""

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_returns_node_info(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should return node status information."""
        from k8s_monitor.tools import get_node_status

        # Create mock node
        mock_node = MagicMock()
        mock_node.metadata.name = "node-1"
        mock_node.metadata.labels = {"node-role.kubernetes.io/control-plane": ""}
        mock_node.status.conditions = [
            MagicMock(type="Ready", status="True"),
            MagicMock(type="MemoryPressure", status="False"),
        ]
        mock_node.status.allocatable = {
            "cpu": "4",
            "memory": "8Gi",
            "pods": "110",
        }

        mock_api = MagicMock()
        mock_api.list_node.return_value = MagicMock(items=[mock_node])
        mock_core_api.return_value = mock_api

        result = get_node_status()

        assert "node-1" in result
        assert result["node-1"]["ready"] is True
        assert result["node-1"]["cpu_allocatable"] == "4 cores"
        assert result["node-1"]["memory_allocatable"] == "8.0 Gi"
        assert "control-plane" in result["node-1"]["roles"]

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_handles_multiple_nodes(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should handle multiple nodes correctly."""
        from k8s_monitor.tools import get_node_status

        mock_nodes = []
        for i in range(3):
            node = MagicMock()
            node.metadata.name = f"node-{i}"
            node.metadata.labels = {}
            node.status.conditions = [MagicMock(type="Ready", status="True")]
            node.status.allocatable = {"cpu": "4", "memory": "8Gi", "pods": "110"}
            mock_nodes.append(node)

        mock_api = MagicMock()
        mock_api.list_node.return_value = MagicMock(items=mock_nodes)
        mock_core_api.return_value = mock_api

        result = get_node_status()

        assert len(result) == 3
        assert all(f"node-{i}" in result for i in range(3))


class TestGetPodStatusSummary:
    """Tests for get_pod_status_summary tool."""

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_counts_by_namespace(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should count pods by namespace and phase."""
        from k8s_monitor.tools import get_pod_status_summary

        # Create pods with explicit attribute return values
        pod1_meta = MagicMock()
        pod1_meta.name = "pod-1"
        pod1_meta.namespace = "default"
        pod1 = MagicMock(metadata=pod1_meta, status=MagicMock(phase="Running", reason=None))

        pod2_meta = MagicMock()
        pod2_meta.name = "pod-2"
        pod2_meta.namespace = "default"
        pod2 = MagicMock(metadata=pod2_meta, status=MagicMock(phase="Running", reason=None))

        pod3_meta = MagicMock()
        pod3_meta.name = "pod-3"
        pod3_meta.namespace = "kube-system"
        pod3 = MagicMock(metadata=pod3_meta, status=MagicMock(phase="Pending", reason="Scheduling"))

        mock_pods = [pod1, pod2, pod3]

        mock_api = MagicMock()
        mock_api.list_pod_for_all_namespaces.return_value = MagicMock(items=mock_pods)
        mock_core_api.return_value = mock_api

        result = get_pod_status_summary()

        assert result["by_namespace"]["default"]["Running"] == 2
        assert result["by_namespace"]["kube-system"]["Pending"] == 1
        assert result["total_problem_pods"] == 1
        assert len(result["problem_pods"]) == 1
        assert result["problem_pods"][0]["name"] == "pod-3"

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_tracks_problem_pods(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should track pending, failed, and unknown pods."""
        from k8s_monitor.tools import get_pod_status_summary

        mock_pods = [
            MagicMock(
                metadata=MagicMock(name="pending-pod", namespace="default"),
                status=MagicMock(phase="Pending", reason="Scheduling"),
            ),
            MagicMock(
                metadata=MagicMock(name="failed-pod", namespace="default"),
                status=MagicMock(phase="Failed", reason="OOMKilled"),
            ),
            MagicMock(
                metadata=MagicMock(name="unknown-pod", namespace="default"),
                status=MagicMock(phase="Unknown", reason=None),
            ),
        ]

        mock_api = MagicMock()
        mock_api.list_pod_for_all_namespaces.return_value = MagicMock(items=mock_pods)
        mock_core_api.return_value = mock_api

        result = get_pod_status_summary()

        assert result["total_problem_pods"] == 3
        phases = {p["phase"] for p in result["problem_pods"]}
        assert phases == {"Pending", "Failed", "Unknown"}


class TestGetRecentEvents:
    """Tests for get_recent_events tool."""

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_returns_formatted_events(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should return properly formatted events."""
        from k8s_monitor.tools import get_recent_events

        mock_event = MagicMock()
        mock_event.type = "Warning"
        mock_event.reason = "FailedScheduling"
        mock_event.message = "No nodes available"
        mock_event.metadata.namespace = "default"
        mock_event.involved_object.kind = "Pod"
        mock_event.involved_object.name = "test-pod"
        mock_event.count = 5
        mock_event.last_timestamp = datetime.now(timezone.utc)
        mock_event.event_time = None

        mock_api = MagicMock()
        mock_api.list_event_for_all_namespaces.return_value = MagicMock(items=[mock_event])
        mock_core_api.return_value = mock_api

        result = get_recent_events(limit=10)

        assert len(result) == 1
        assert result[0]["type"] == "Warning"
        assert result[0]["reason"] == "FailedScheduling"
        assert result[0]["involved_object"] == "Pod/test-pod"


class TestGetDeploymentStatus:
    """Tests for get_deployment_status tool."""

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.AppsV1Api")
    def test_identifies_healthy_deployments(
        self, mock_apps_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should correctly identify healthy deployments."""
        from k8s_monitor.tools import get_deployment_status

        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "my-app"
        mock_deployment.metadata.namespace = "default"
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 3
        mock_deployment.status.available_replicas = 3

        mock_api = MagicMock()
        mock_api.list_deployment_for_all_namespaces.return_value = MagicMock(
            items=[mock_deployment]
        )
        mock_apps_api.return_value = mock_api

        result = get_deployment_status()

        assert result["healthy_count"] == 1
        assert result["unhealthy_count"] == 0

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.AppsV1Api")
    def test_identifies_unhealthy_deployments(
        self, mock_apps_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should correctly identify unhealthy deployments."""
        from k8s_monitor.tools import get_deployment_status

        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "failing-app"
        mock_deployment.metadata.namespace = "default"
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 1
        mock_deployment.status.available_replicas = 1

        mock_api = MagicMock()
        mock_api.list_deployment_for_all_namespaces.return_value = MagicMock(
            items=[mock_deployment]
        )
        mock_apps_api.return_value = mock_api

        result = get_deployment_status()

        assert result["healthy_count"] == 0
        assert result["unhealthy_count"] == 1
        assert result["unhealthy_deployments"][0]["name"] == "failing-app"


class TestGetResourceUsage:
    """Tests for get_resource_usage tool."""

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_calculates_resource_totals(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should calculate total CPU and memory requests/limits."""
        from k8s_monitor.tools import get_resource_usage

        mock_container = MagicMock()
        mock_container.resources.requests = {"cpu": "500m", "memory": "1Gi"}
        mock_container.resources.limits = {"cpu": "1000m", "memory": "2Gi"}

        mock_pod = MagicMock()
        mock_pod.status.phase = "Running"
        mock_pod.spec.containers = [mock_container]

        mock_api = MagicMock()
        mock_api.list_pod_for_all_namespaces.return_value = MagicMock(items=[mock_pod])
        mock_core_api.return_value = mock_api

        result = get_resource_usage()

        assert result["cpu_requests_cores"] == 0.5
        assert result["cpu_limits_cores"] == 1.0
        assert result["memory_requests_gb"] == 1.0
        assert result["memory_limits_gb"] == 2.0


class TestGetPvcStatus:
    """Tests for get_pvc_status tool."""

    @patch("k8s_monitor.tools._load_k8s_config")
    @patch("k8s_monitor.tools.client.CoreV1Api")
    def test_counts_bound_pvcs(
        self, mock_core_api: MagicMock, mock_load_config: MagicMock
    ) -> None:
        """Should count bound and problem PVCs."""
        from k8s_monitor.tools import get_pvc_status

        # Create PVCs with explicit attribute values
        pvc1_meta = MagicMock()
        pvc1_meta.name = "data-pvc"
        pvc1_meta.namespace = "default"
        pvc1 = MagicMock(
            metadata=pvc1_meta,
            status=MagicMock(phase="Bound", capacity={"storage": "10Gi"}),
        )

        pvc2_meta = MagicMock()
        pvc2_meta.name = "pending-pvc"
        pvc2_meta.namespace = "default"
        pvc2 = MagicMock(
            metadata=pvc2_meta,
            status=MagicMock(phase="Pending", capacity=None),
        )

        mock_pvcs = [pvc1, pvc2]

        mock_api = MagicMock()
        mock_api.list_persistent_volume_claim_for_all_namespaces.return_value = MagicMock(
            items=mock_pvcs
        )
        mock_core_api.return_value = mock_api

        result = get_pvc_status()

        assert result["bound_count"] == 1
        assert result["problem_count"] == 1
        assert result["problem_pvcs"][0]["name"] == "pending-pvc"
