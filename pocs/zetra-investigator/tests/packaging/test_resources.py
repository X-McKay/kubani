from importlib.resources import files


def test_agent_resources_are_available():
    resources = files("kubani_investigator.agents.investigator")
    assert "investigator" in resources.joinpath("agent.yaml").read_text()
    assert resources.joinpath("instructions/base.md").read_text().strip()
