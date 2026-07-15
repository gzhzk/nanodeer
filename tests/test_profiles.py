import pytest

from nanodeer.profiles import (
    DEFAULT_CAPABILITIES,
    compose_profile,
    normalize_capabilities,
)


def test_default_bundle_combines_all_domains_without_duplicate_tools():
    profile = compose_profile()
    names = [tool.name for tool in profile.tools]

    assert profile.capabilities == DEFAULT_CAPABILITIES
    assert len(names) == len(set(names))
    assert {
        "bash",
        "web_search",
        "office_artifact",
        "tasks",
        "save_memory",
        "invoke_skill",
        "wait",
    } <= set(names)
    assert {"code_project", "research_report", "office_artifacts", "daily_planning"} <= set(
        profile.skills
    )


def test_subset_only_exposes_selected_domain_tools():
    profile = compose_profile(["research"])
    names = {tool.name for tool in profile.tools}

    assert profile.capabilities == ("research",)
    assert "web_search" in names
    assert "bash" not in names
    assert "save_memory" not in names
    assert {"wait", "invoke_skill"} <= names


def test_aliases_and_comma_separated_values():
    assert normalize_capabilities("coding,research") == ("coding", "research")
    assert normalize_capabilities("all") == DEFAULT_CAPABILITIES
    assert normalize_capabilities([]) == DEFAULT_CAPABILITIES


def test_unknown_capability_is_rejected():
    with pytest.raises(ValueError, match="Unknown capability 'magic'"):
        compose_profile(["magic"])
