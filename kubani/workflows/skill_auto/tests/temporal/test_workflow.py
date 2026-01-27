"""Tests for SkillAutoWorkflow."""


def test_skill_auto_workflow_has_required_methods():
    """SkillAutoWorkflow should have run, get_state, and signal methods."""
    from kubani.workflows.skill_auto import SkillAutoWorkflow

    assert hasattr(SkillAutoWorkflow, "run")
    assert hasattr(SkillAutoWorkflow, "get_state")
    assert hasattr(SkillAutoWorkflow, "pause")
    assert hasattr(SkillAutoWorkflow, "resume")
    assert hasattr(SkillAutoWorkflow, "cancel")


def test_skill_auto_workflow_decorated():
    """SkillAutoWorkflow should be decorated with @workflow.defn."""
    from kubani.workflows.skill_auto import SkillAutoWorkflow

    # Check if class has workflow metadata
    assert hasattr(SkillAutoWorkflow, "__temporal_workflow_definition")
