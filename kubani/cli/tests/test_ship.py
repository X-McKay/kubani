"""Tests for ShipOrchestrator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kubani.cli.components import ComponentInfo, ComponentRegistry
from kubani.cli.ship import ShipOrchestrator, ShipPhase, ShipResult


@pytest.fixture
def mock_component():
    return ComponentInfo(
        name="temporal-mcp-server",
        type="mcp-server",
        source="kubani/mcp/servers/temporal",
        earthfile="kubani/mcp/servers/temporal/Earthfile",
        package="temporal-mcp-server",
        image_name="temporal-mcp-server",
        deployment="infrastructure/gitops/apps/ai-agents/temporal-mcp-server/deployment.yaml",
        namespace="ai-agents",
    )


@pytest.fixture
def mock_registry(mock_component):
    reg = MagicMock(spec=ComponentRegistry)
    reg.get.return_value = mock_component
    reg.all_names.return_value = ["temporal-mcp-server"]
    reg.project_root = Path("/fake")
    return reg


def test_ship_result_defaults():
    result = ShipResult(component="test", phase=ShipPhase.PENDING)
    assert result.success is False
    assert result.image_tag == ""


def test_ship_phases_ordering():
    """Verify ship phases are in the expected order."""
    phases = list(ShipPhase)
    assert phases[0] == ShipPhase.PENDING
    assert phases[1] == ShipPhase.PREFLIGHT
    assert phases[2] == ShipPhase.BUMPING
    assert phases[3] == ShipPhase.TESTING
    assert phases[4] == ShipPhase.BUILDING
    assert phases[5] == ShipPhase.PUSHING
    assert phases[6] == ShipPhase.PATCHING
    assert phases[7] == ShipPhase.COMMITTING
    assert phases[8] == ShipPhase.VERIFYING
    assert phases[9] == ShipPhase.DONE
    assert phases[10] == ShipPhase.FAILED


@pytest.mark.asyncio
async def test_ship_unknown_component():
    reg = MagicMock(spec=ComponentRegistry)
    reg.get.return_value = None
    reg.all_names.return_value = []
    reg.project_root = Path("/fake")

    ship = ShipOrchestrator(reg)
    result = await ship.ship("nonexistent")
    assert result.phase == ShipPhase.FAILED
    assert "not found" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_staged_changes_rejected(mock_registry):
    """Ship should fail if there are staged git changes."""
    ship = ShipOrchestrator(mock_registry)
    with patch.object(ship, "_check_clean_staging", return_value=False):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.FAILED
    assert "staged" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_test_failure(mock_registry):
    ship = ShipOrchestrator(mock_registry)
    with (
        patch.object(ship, "_check_clean_staging", return_value=True),
        patch.object(ship, "_bump_version", return_value=True),
        patch.object(ship, "_run_tests", return_value=False),
    ):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.FAILED
    assert "test" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_build_failure(mock_registry):
    ship = ShipOrchestrator(mock_registry)
    with (
        patch.object(ship, "_check_clean_staging", return_value=True),
        patch.object(ship, "_bump_version", return_value=True),
        patch.object(ship, "_run_tests", return_value=True),
        patch.object(ship, "_build_and_push", return_value=(False, "")),
    ):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.FAILED
    assert "build" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_skip_test(mock_registry):
    """When skip_test=True, tests should not run."""
    ship = ShipOrchestrator(mock_registry)
    with (
        patch.object(ship, "_check_clean_staging", return_value=True),
        patch.object(ship, "_bump_version", return_value=True),
        patch.object(ship, "_run_tests") as mock_test,
        patch.object(ship, "_build_and_push", return_value=(True, "1.0.0-abc")),
        patch.object(ship, "_patch_manifest", return_value=True),
        patch.object(ship, "_commit_manifest", return_value=True),
        patch.object(ship, "_git_push", return_value=True),
        patch.object(ship, "_verify_deployment", return_value=True),
    ):
        result = await ship.ship("temporal-mcp-server", skip_test=True)
    mock_test.assert_not_called()
    assert result.phase == ShipPhase.DONE


@pytest.mark.asyncio
async def test_ship_skip_verify(mock_registry):
    """When skip_verify=True, verification should not run."""
    ship = ShipOrchestrator(mock_registry)
    with (
        patch.object(ship, "_check_clean_staging", return_value=True),
        patch.object(ship, "_bump_version", return_value=True),
        patch.object(ship, "_run_tests", return_value=True),
        patch.object(ship, "_build_and_push", return_value=(True, "1.0.0-abc")),
        patch.object(ship, "_patch_manifest", return_value=True),
        patch.object(ship, "_commit_manifest", return_value=True),
        patch.object(ship, "_git_push", return_value=True),
        patch.object(ship, "_verify_deployment") as mock_verify,
    ):
        result = await ship.ship("temporal-mcp-server", skip_verify=True)
    mock_verify.assert_not_called()
    assert result.phase == ShipPhase.DONE


@pytest.mark.asyncio
async def test_ship_dry_run(mock_registry):
    """Dry run should run preflight + tests only, no build/push/deploy."""
    ship = ShipOrchestrator(mock_registry)
    with (
        patch.object(ship, "_check_clean_staging", return_value=True),
        patch.object(ship, "_run_tests", return_value=True),
        patch.object(ship, "_build_and_push") as mock_build,
    ):
        result = await ship.ship("temporal-mcp-server", dry_run=True)
    mock_build.assert_not_called()
    assert result.phase == ShipPhase.DONE
    assert "dry" in result.message.lower()


@pytest.mark.asyncio
async def test_ship_happy_path(mock_registry):
    """Full ship pipeline succeeds."""
    ship = ShipOrchestrator(mock_registry)
    with (
        patch.object(ship, "_check_clean_staging", return_value=True),
        patch.object(ship, "_bump_version", return_value=True),
        patch.object(ship, "_run_tests", return_value=True),
        patch.object(ship, "_build_and_push", return_value=(True, "1.0.1-abc1234")),
        patch.object(ship, "_patch_manifest", return_value=True),
        patch.object(ship, "_commit_manifest", return_value=True),
        patch.object(ship, "_git_push", return_value=True),
        patch.object(ship, "_verify_deployment", return_value=True),
    ):
        result = await ship.ship("temporal-mcp-server")
    assert result.phase == ShipPhase.DONE
    assert result.success is True
    assert result.image_tag == "1.0.1-abc1234"
