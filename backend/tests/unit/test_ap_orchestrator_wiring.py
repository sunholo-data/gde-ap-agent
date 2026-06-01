"""Work item 3.1 — AP orchestrator sub-agent wiring (GDE Track 3).

Three assertions that would have caught the original wiring bugs:

1. _parse_template on ap-orchestrator/SKILL.md yields sub_skills in the
   expected order.
2. After seeding, create_agent("ap-orchestrator") returns an LlmAgent
   whose sub_agents are named docparse / ap-validator / ap-poster in that
   order.
3. create_agent("ap-validator") returns an LlmAgent whose tools include
   an AgentTool wrapping an agent named enterprise_search_agent — proving
   `datastore_id` is read from toolConfigs (not the old buggy `datastore`
   key).

All three run in LOCAL_MODE (no GCP, no network).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from admin.platform_seed import _parse_template
from auth.firebase_auth import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _local_mode(monkeypatch):
    monkeypatch.setenv("LOCAL_MODE", "1")
    from db import firestore

    firestore._reset_client_for_testing()
    yield
    firestore._reset_client_for_testing()


@pytest.fixture
def _seeded_ap_skills():
    """Seed the AP skill bundle into the in-memory Firestore."""
    import time

    from db.local_fixture import _seed_ap_skills

    _seed_ap_skills(time.time())


def _test_user() -> User:
    return User(uid="test-user", email="test@example.com", domain="example.com")


_TEMPLATES_ROOT = Path(__file__).resolve().parents[2] / "skills" / "templates"


# ---------------------------------------------------------------------------
# 1. Template parse
# ---------------------------------------------------------------------------


def test_parse_ap_orchestrator_template_has_correct_sub_skills():
    parsed = _parse_template(_TEMPLATES_ROOT / "ap-orchestrator" / "SKILL.md")
    sub_skills = parsed["metadata"].get("subSkills", [])
    assert sub_skills == ["docparse", "ap-validator", "ap-poster"], (
        f"Expected ['docparse', 'ap-validator', 'ap-poster'], got {sub_skills!r}"
    )


# ---------------------------------------------------------------------------
# 2. Orchestrator sub-agent wiring
# ---------------------------------------------------------------------------


def test_create_agent_ap_orchestrator_has_correct_sub_agents(_seeded_ap_skills):
    from adk.agent import _safe_agent_name, create_agent
    from skills.skill_config import find_by_name

    config = find_by_name("ap-orchestrator")
    assert config is not None, "ap-orchestrator not seeded"

    agent = create_agent(config, _test_user())

    assert isinstance(agent, LlmAgent)
    sub_names = [s.name for s in agent.sub_agents]
    expected = [
        _safe_agent_name("docparse"),
        _safe_agent_name("ap-validator"),
        _safe_agent_name("ap-poster"),
    ]
    assert sub_names == expected, f"Expected sub_agent names {expected!r}, got {sub_names!r}"


# ---------------------------------------------------------------------------
# 3. Validator has enterprise_search_agent tool (datastore_id wired)
# ---------------------------------------------------------------------------


def test_create_agent_ap_validator_has_enterprise_search_agent(_seeded_ap_skills):
    from adk.agent import create_agent
    from skills.skill_config import find_by_name

    config = find_by_name("ap-validator")
    assert config is not None, "ap-validator not seeded"

    agent = create_agent(config, _test_user())

    assert isinstance(agent, LlmAgent)
    agent_tool_names = [t.agent.name for t in agent.tools if isinstance(t, AgentTool)]
    assert "enterprise_search_agent" in agent_tool_names, (
        f"Expected 'enterprise_search_agent' in AgentTool names, got {agent_tool_names!r}. "
        "Check that ap-validator/SKILL.md toolConfigs.ai_search.datastore_id is set "
        "(not the old buggy 'datastore' key)."
    )
