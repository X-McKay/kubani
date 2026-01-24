"""Tests for TemporalMCPClient."""

import httpx
import pytest

from framework.mcp.client import TemporalMCPClient


class TestTemporalMCPClientListWorkflows:
    """Test list_workflows functionality"""

    @pytest.mark.asyncio
    async def test_list_workflows_with_no_filters(self, respx_mock):
        """list_workflows should call temporal MCP with correct parameters"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": {
                        "workflows": [
                            {"id": "wf-1", "status": "running"},
                            {"id": "wf-2", "status": "completed"},
                        ]
                    }
                },
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.list_workflows()

        assert response.success is True
        assert len(response.data["workflows"]) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_list_workflows_with_status_filter(self, respx_mock):
        """list_workflows should pass status filter to MCP server"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"workflows": [{"id": "wf-1", "status": "running"}]}},
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.list_workflows(status="running")

        assert response.success is True
        assert len(response.data["workflows"]) == 1
        await client.close()


class TestTemporalMCPClientWorkflowOperations:
    """Test workflow CRUD operations"""

    @pytest.mark.asyncio
    async def test_get_workflow_by_id(self, respx_mock):
        """get_workflow should retrieve workflow details"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"id": "wf-123", "status": "running", "history": []}},
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.get_workflow("wf-123")

        assert response.success is True
        assert response.data["id"] == "wf-123"
        await client.close()

    @pytest.mark.asyncio
    async def test_start_workflow(self, respx_mock):
        """start_workflow should start new workflow"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"workflow_id": "wf-new", "run_id": "run-123"}},
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.start_workflow(
            workflow_type="MyWorkflow",
            workflow_id="wf-new",
            task_queue="default",
            args=[{"param": "value"}],
        )

        assert response.success is True
        assert response.data["workflow_id"] == "wf-new"
        await client.close()

    @pytest.mark.asyncio
    async def test_signal_workflow(self, respx_mock):
        """signal_workflow should send signal to workflow"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"success": True}})
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.signal_workflow("wf-123", "pause", [{"reason": "maintenance"}])

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, respx_mock):
        """cancel_workflow should cancel running workflow"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(200, json={"content": {"cancelled": True}})
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.cancel_workflow("wf-123")

        assert response.success is True
        await client.close()

    @pytest.mark.asyncio
    async def test_list_schedules(self, respx_mock):
        """list_schedules should retrieve schedule list"""
        respx_mock.post("http://localhost:8081/tools/call").mock(
            return_value=httpx.Response(
                200,
                json={"content": {"schedules": [{"id": "sched-1"}, {"id": "sched-2"}]}},
            )
        )

        client = TemporalMCPClient("temporal", "http://localhost:8081")
        response = await client.list_schedules(limit=50)

        assert response.success is True
        assert len(response.data["schedules"]) == 2
        await client.close()
