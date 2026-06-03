"""AP orchestrator sub-agent wiring (GDE Track 3).

Original Work item 3.1 (flat orchestrator → 3 specialists) was reworked by
WORKFLOW-PIPELINE into a two-level hierarchy:

    ap-orchestrator (LlmAgent, conversational front door)
        └── ap-pipeline (SequentialAgent, deterministic)
                ├── invoice-extractor
                ├── ap-validator
                └── ap-poster

The assertions below mirror the new structure end-to-end:

1. ap-orchestrator/SKILL.md.subSkills == ["ap-pipeline"] (one transfer, not three).
2. create_agent("ap-orchestrator") is an LlmAgent with one sub_agent (ap-pipeline).
3. That sub_agent is a SequentialAgent whose own sub_agents are the three
   specialists in Extract → Validate → Post order.
4. ap-validator still has the enterprise_search_agent AgentTool (regression
   guard for the datastore_id wiring bug).

All run in LOCAL_MODE (no GCP, no network).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from google.adk.agents import LlmAgent, SequentialAgent
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


def test_parse_ap_orchestrator_template_points_to_ap_pipeline():
    """Orchestrator delegates to ap-pipeline only — one transfer per
    processing request, not three (which was the bug)."""
    parsed = _parse_template(_TEMPLATES_ROOT / "ap-orchestrator" / "SKILL.md")
    sub_skills = parsed["metadata"].get("subSkills", [])
    assert sub_skills == ["ap-pipeline"], f"Expected ['ap-pipeline'], got {sub_skills!r}"


def test_parse_ap_pipeline_template_has_specialists_in_order():
    """ap-pipeline (the SequentialAgent) walks Extract → Validate → Post."""
    parsed = _parse_template(_TEMPLATES_ROOT / "ap-pipeline" / "SKILL.md")
    sub_skills = parsed["metadata"].get("subSkills", [])
    assert sub_skills == ["invoice-extractor", "ap-validator", "ap-poster"], (
        f"Expected three specialists in order, got {sub_skills!r}"
    )
    assert parsed["metadata"].get("agentType") == "sequential"


# ---------------------------------------------------------------------------
# 2. Two-level wiring: orchestrator → pipeline → specialists
# ---------------------------------------------------------------------------


def test_create_agent_ap_orchestrator_transfers_to_single_pipeline(_seeded_ap_skills):
    """ap-orchestrator is an LlmAgent with exactly one sub_agent: ap-pipeline."""
    from adk.agent import _safe_agent_name, create_agent
    from skills.skill_config import find_by_name

    config = find_by_name("ap-orchestrator")
    assert config is not None, "ap-orchestrator not seeded"

    agent = create_agent(config, _test_user())

    assert isinstance(agent, LlmAgent)
    sub_names = [s.name for s in agent.sub_agents]
    assert sub_names == [_safe_agent_name("ap-pipeline")], f"Expected orchestrator → [ap-pipeline], got {sub_names!r}"


def test_create_agent_ap_pipeline_is_sequential_with_three_specialists(_seeded_ap_skills):
    """ap-pipeline is a SequentialAgent whose sub_agents are the three specialists
    in Extract → Validate → Post order. This is the deterministic backbone."""
    from adk.agent import _safe_agent_name, create_agent
    from skills.skill_config import find_by_name

    config = find_by_name("ap-pipeline")
    assert config is not None, "ap-pipeline not seeded"

    agent = create_agent(config, _test_user())

    assert isinstance(agent, SequentialAgent)
    sub_names = [s.name for s in agent.sub_agents]
    expected = [
        _safe_agent_name("invoice-extractor"),
        _safe_agent_name("ap-validator"),
        _safe_agent_name("ap-poster"),
    ]
    assert sub_names == expected, f"Expected pipeline → {expected!r}, got {sub_names!r}"


def test_create_agent_orchestrator_pipeline_specialists_chain(_seeded_ap_skills):
    """End-to-end: orchestrator's sub_agent is the pipeline; the pipeline's
    sub_agents are the three specialists. Walks the full tree the way the
    runtime will."""
    from adk.agent import _safe_agent_name, create_agent
    from skills.skill_config import find_by_name

    orchestrator = create_agent(find_by_name("ap-orchestrator"), _test_user())
    assert isinstance(orchestrator, LlmAgent)
    assert len(orchestrator.sub_agents) == 1

    pipeline = orchestrator.sub_agents[0]
    assert isinstance(pipeline, SequentialAgent)
    assert pipeline.name == _safe_agent_name("ap-pipeline")

    specialist_names = [s.name for s in pipeline.sub_agents]
    assert specialist_names == [
        _safe_agent_name("invoice-extractor"),
        _safe_agent_name("ap-validator"),
        _safe_agent_name("ap-poster"),
    ]


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
