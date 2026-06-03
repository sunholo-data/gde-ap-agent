"""Unit tests for create_agent() (AGENT-FACTORY M2).

The factory assembles an ADK LlmAgent from a SkillConfig + authenticated
User. It reads from `skill_metadata.*`, wires a per-user
`before_tool_callback` via `make_permission_enforcer`, and recurses into
sub-skills (resolved by ID through `skills.skill_config.get_skill`) with
cycle detection.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from a2ui.adk.send_a2ui_to_client_toolset import SendA2uiToClientToolset
from google.adk.agents import LlmAgent

from adk.agent import _safe_agent_name, create_agent
from auth.firebase_auth import User
from db.models import SkillConfig, SkillMetadata


def _user() -> User:
    return User(uid="u1", email="alice@example.com", domain="example.com")


def _skill(
    name: str = "test-skill",
    skill_id: str = "11111111-1111-1111-1111-111111111111",
    tools: list[str] | None = None,
    sub_skills: list[str] | None = None,
    model: str = "gemini-2.5-flash",
    thinking_model: str | None = None,
    instructions: str = "Do the thing.",
    tool_configs: dict | None = None,
    agent_type: str = "llm",
) -> SkillConfig:
    return SkillConfig(
        name=name,
        description="Test skill for unit tests.",
        instructions=instructions,
        skillId=skill_id,
        skillMetadata=SkillMetadata(
            model=model,
            thinkingModel=thinking_model,
            tools=tools or [],
            subSkills=sub_skills or [],
            toolConfigs=tool_configs or {},
            agentType=agent_type,
        ),
    )


# --- _safe_agent_name ---


def test_safe_agent_name_converts_hyphens_to_underscores():
    # Skill IDs default to UUIDs with hyphens, ADK rejects hyphens.
    assert _safe_agent_name("abc-123-def") == "abc_123_def"


def test_safe_agent_name_prepends_underscore_when_starts_with_digit():
    # UUIDs can start with a digit; ADK names must start with letter/underscore.
    safe = _safe_agent_name("1abc-def")
    assert safe.startswith(("s_", "_"))
    assert "-" not in safe


def test_safe_agent_name_leaves_valid_identifiers_unchanged():
    assert _safe_agent_name("already_valid") == "already_valid"


# --- happy path ---


def test_create_agent_returns_llmagent_with_expected_name_and_instruction():
    agent = create_agent(_skill(), _user())
    assert isinstance(agent, LlmAgent)
    # name is a sanitized skill_id (hyphens -> underscores)
    assert agent.name == _safe_agent_name("11111111-1111-1111-1111-111111111111")
    # Instruction is now an InstructionProvider (sprint 1.25 wraps the
    # static string with `wrap_with_iframe_context` so the runtime can
    # inject `mcp_app_context.*` state at agent-instruction-build time).
    # When session state has no `mcp_app_context.*` keys (the common
    # case), the wrapper returns the base string unchanged. Resolve the
    # callable with a stub ReadonlyContext to assert that contract.
    import asyncio
    from unittest.mock import MagicMock

    assert callable(agent.instruction)
    fake_ctx = MagicMock()
    fake_ctx.state = {}
    # asyncio.run rather than get_event_loop().run_until_complete — the
    # latter relies on the deprecated default-loop-on-main-thread that
    # gets closed by pytest-asyncio fixtures in other tests, leading to
    # "no current event loop" failures that depend on suite ordering.
    resolved = asyncio.run(agent.instruction(fake_ctx))
    assert resolved == "Do the thing."


def test_create_agent_instruction_appends_iframe_context_when_state_has_it():
    """End-to-end: when session state carries `mcp_app_context.*` keys
    (because an MCP App iframe pushed `ui/update-model-context`), the
    agent's runtime instruction MUST include the iframe-context block
    so the model can reference what's currently on screen.

    Sprint 1.25 — pairs with the iframe-context endpoint and the
    frontend `onFallbackRequest` handler."""
    import asyncio
    from unittest.mock import MagicMock

    agent = create_agent(_skill(), _user())
    fake_ctx = MagicMock()
    fake_ctx.state = {
        "mcp_app_context.ext-apps-map.show-map": {
            "structuredContent": {"label": "Munich", "viewUUID": "abc-123"},
        },
    }
    resolved = asyncio.run(agent.instruction(fake_ctx))
    assert resolved.startswith("Do the thing.")
    assert "Current iframe-app context" in resolved
    assert "Munich" in resolved
    assert "ext-apps-map.show-map" in resolved


def test_create_agent_instruction_appends_a2ui_surface_context_when_state_has_it():
    """Sprint 2.10 sibling of the iframe-context test above. When session
    state carries A2UI surface data (either per-turn snapshot under
    ``a2ui_surface_state`` OR persisted action writes under
    ``a2ui_surface_context.{surface}.*``), the agent's runtime
    instruction MUST include the surface-context block so the model
    knows what surfaces the user is viewing."""
    import asyncio
    from unittest.mock import MagicMock

    agent = create_agent(_skill(), _user())
    fake_ctx = MagicMock()
    fake_ctx.state = {
        "a2ui_surface_state": {
            "workspace": {"dataModel": {"activeUsers": "42 users online"}},
        },
        "a2ui_surface_context.workspace.lastAction": {
            "name": "approve",
            "sourceComponentId": "row-47",
        },
    }
    resolved = asyncio.run(agent.instruction(fake_ctx))
    assert resolved.startswith("Do the thing.")
    # A2UI block prose
    assert "A2UI surface state" in resolved
    # Per-turn dataModel content
    assert "42 users online" in resolved
    # Persisted action content
    assert "approve" in resolved
    assert "row-47" in resolved
    # Single workspace heading — both sources merged, not stacked
    assert resolved.count("## workspace") == 1


def test_create_agent_instruction_appends_both_iframe_and_a2ui_blocks():
    """Chain coexistence: when state has BOTH mcp_app_context.* AND
    a2ui_surface_state, the agent prompt carries BOTH blocks. The two
    InstructionProvider wrappers are independent — each appends its
    own block in order (iframe first, A2UI second)."""
    import asyncio
    from unittest.mock import MagicMock

    agent = create_agent(_skill(), _user())
    fake_ctx = MagicMock()
    fake_ctx.state = {
        "mcp_app_context.ext-apps-map.show-map": {
            "structuredContent": {"label": "Munich"},
        },
        "a2ui_surface_state": {
            "workspace": {"dataModel": {"revenue": "$1,234"}},
        },
    }
    resolved = asyncio.run(agent.instruction(fake_ctx))
    assert resolved.startswith("Do the thing.")
    assert "Current iframe-app context" in resolved
    assert "Munich" in resolved
    assert "A2UI surface state" in resolved
    assert "$1,234" in resolved
    # iframe block appears first (inner wrapper appends earlier)
    assert resolved.index("iframe-app context") < resolved.index("A2UI surface state")


def test_create_agent_includes_a2ui_toolset():
    """A2UI is delivered via SendA2uiToClientToolset tool calls, not fenced blocks."""
    agent = create_agent(_skill(), _user())
    a2ui_toolsets = [t for t in agent.tools if isinstance(t, SendA2uiToClientToolset)]
    assert len(a2ui_toolsets) == 1


def test_create_agent_wires_tools_from_skill_metadata():
    # list_documents + get_document_content are in the registry (model-agnostic).
    # ai_search/google_search are model-aware and handled by agent.py directly, so not here.
    agent = create_agent(_skill(tools=["list_documents", "get_document_content"]), _user())
    # Defaults from agent.py: load_artifacts_tool + retrieve_artifact +
    # load_memory_tool + preload_memory_tool. Plus 2 registry tools and
    # SendA2uiToClientToolset = 7 total.
    assert len(agent.tools) == 7
    tool_names = _tool_ids(agent)
    assert "load_artifacts" in tool_names
    assert "load_memory" in tool_names
    assert "preload_memory" in tool_names


def _tool_ids(agent) -> list[str]:
    """Return a list of identifiers for each tool in agent.tools.

    ADK tools may be raw functions (use __name__) or FunctionTool/built-in
    objects (use .name). This helper normalises both so tests aren't brittle
    against ADK's internal wrapping choices.
    """
    ids = []
    for t in agent.tools:
        ids.append(getattr(t, "name", None) or getattr(t, "__name__", type(t).__name__))
    return ids


def test_create_agent_search_uses_sub_agent_pattern():
    """Search skills use AgentTool(search_agent) for all models — keeps root agent
    FunctionTool-compatible so retrieve_artifact and a2ui coexist with search."""
    from google.adk.tools import AgentTool

    agent = create_agent(_skill(tools=["google_search"], model="gemini-2.5-flash"), _user())
    tool_ids = _tool_ids(agent)
    # FunctionTools are NOT excluded — search goes via sub-agent
    assert "retrieve_artifact" in tool_ids
    a2ui_toolsets = [t for t in agent.tools if isinstance(t, SendA2uiToClientToolset)]
    assert len(a2ui_toolsets) == 1
    # Search is delivered as an AgentTool wrapping the search_agent sub-agent
    agent_tools = [t for t in agent.tools if isinstance(t, AgentTool)]
    assert any(getattr(t.agent, "name", None) == "web_search_agent" for t in agent_tools)


def test_create_agent_non_gemini_search_retains_retrieve_artifact():
    """Non-search Gemini skills should still get retrieve_artifact."""
    agent = create_agent(_skill(tools=["list_documents"], model="gemini-2.5-flash"), _user())
    assert "retrieve_artifact" in _tool_ids(agent)


def test_create_agent_unknown_tool_raises():
    """Unknown tool names raise ValueError to prevent silent misconfiguration."""
    with pytest.raises(ValueError, match="not_a_real_tool"):
        create_agent(_skill(tools=["list_documents", "not_a_real_tool"]), _user())


def test_create_agent_attaches_permission_enforcer_callback():
    agent = create_agent(_skill(), _user())
    # ADK may coerce a single callback into a list; handle both.
    cb = agent.before_tool_callback
    assert cb is not None
    if isinstance(cb, list):
        assert len(cb) >= 1
    else:
        assert callable(cb)


# --- sub-agent recursion ---


def test_create_agent_recurses_into_sub_skills():
    child = _skill(name="child-skill", skill_id="child-id", instructions="child work")
    parent = _skill(name="parent-skill", skill_id="parent-id", sub_skills=["child-id"])
    with patch("adk.agent.get_skill", return_value=child):
        agent = create_agent(parent, _user())
    assert len(agent.sub_agents) == 1
    assert agent.sub_agents[0].name == _safe_agent_name("child-id")


def test_create_agent_missing_sub_skill_warns_and_skips(caplog):
    parent = _skill(name="parent-skill", skill_id="parent-id", sub_skills=["missing-id"])
    with patch("adk.agent.get_skill", return_value=None):
        with caplog.at_level(logging.WARNING):
            agent = create_agent(parent, _user())
    assert agent.sub_agents == []
    assert any("missing-id" in rec.message for rec in caplog.records)


def test_create_agent_detects_direct_self_cycle():
    # Skill references itself as a sub-skill — must raise.
    skill = _skill(name="loop-skill", skill_id="loop-id", sub_skills=["loop-id"])
    with patch("adk.agent.get_skill", return_value=skill):
        with pytest.raises(ValueError, match="Sub-skill cycle detected"):
            create_agent(skill, _user())


def test_create_agent_detects_indirect_cycle():
    a = _skill(name="a-skill", skill_id="a-id", sub_skills=["b-id"])
    b = _skill(name="b-skill", skill_id="b-id", sub_skills=["a-id"])
    lookup = {"a-id": a, "b-id": b}
    with patch("adk.agent.get_skill", side_effect=lambda sid: lookup.get(sid)):
        with pytest.raises(ValueError, match="Sub-skill cycle detected"):
            create_agent(a, _user())


# --- tool opt-out (template-hardening M1) ---


def test_create_agent_a2ui_disabled_removes_toolset():
    """toolConfigs.a2ui.enabled: false → no SendA2uiToClientToolset attached."""
    skill = _skill(tool_configs={"a2ui": {"enabled": False}})
    agent = create_agent(skill, _user())
    a2ui_toolsets = [t for t in agent.tools if isinstance(t, SendA2uiToClientToolset)]
    assert len(a2ui_toolsets) == 0
    # send_a2ui_json_to_client must not appear in any tool name
    assert "send_a2ui_json_to_client" not in _tool_ids(agent)


def test_create_agent_a2ui_enabled_by_default():
    """No toolConfigs key → A2UI toolset still attached (backwards compat)."""
    agent = create_agent(_skill(), _user())
    a2ui_toolsets = [t for t in agent.tools if isinstance(t, SendA2uiToClientToolset)]
    assert len(a2ui_toolsets) == 1


def test_create_agent_defaults_artifacts_false_removes_artifact_tools():
    """toolConfigs.defaults.artifacts: false → load_artifacts + retrieve_artifact absent."""
    skill = _skill(tool_configs={"defaults": {"artifacts": False}})
    agent = create_agent(skill, _user())
    ids = _tool_ids(agent)
    assert "load_artifacts" not in ids
    assert "retrieve_artifact" not in ids
    # Memory tools still present (only artifacts opted out)
    assert "load_memory" in ids
    assert "preload_memory" in ids


def test_create_agent_defaults_memory_false_removes_memory_tools():
    """toolConfigs.defaults.memory: false → load_memory + preload_memory absent."""
    skill = _skill(tool_configs={"defaults": {"memory": False}})
    agent = create_agent(skill, _user())
    ids = _tool_ids(agent)
    assert "load_memory" not in ids
    assert "preload_memory" not in ids
    # Artifact tools still present
    assert "load_artifacts" in ids
    assert "retrieve_artifact" in ids


def test_create_agent_defaults_all_false_removes_all_default_tools():
    """toolConfigs.defaults.artifacts: false + memory: false → only skill tools + A2UI."""
    skill = _skill(
        tools=["list_documents"],
        tool_configs={"defaults": {"artifacts": False, "memory": False}},
    )
    agent = create_agent(skill, _user())
    ids = _tool_ids(agent)
    assert "load_artifacts" not in ids
    assert "retrieve_artifact" not in ids
    assert "load_memory" not in ids
    assert "preload_memory" not in ids
    # list_documents still present; A2UI still present
    assert "list_documents" in ids


def test_create_agent_no_tool_configs_includes_all_defaults():
    """No toolConfigs → all four default tools present (backwards compat)."""
    agent = create_agent(_skill(), _user())
    ids = _tool_ids(agent)
    assert "load_artifacts" in ids
    assert "retrieve_artifact" in ids
    assert "load_memory" in ids
    assert "preload_memory" in ids


# --- WORKFLOW-PIPELINE M1: SequentialAgent build path ---


def test_create_agent_sequential_returns_sequential_agent():
    """agent_type=sequential builds a SequentialAgent, not an LlmAgent.

    The pipeline skill has no model/tools/instruction — its only job is to
    walk sub_skills deterministically. ADK's SequentialAgent does that for us.
    """
    from google.adk.agents import SequentialAgent

    extractor = _skill(name="extractor", skill_id="extractor-id", instructions="extract")
    validator = _skill(name="validator", skill_id="validator-id", instructions="validate")
    pipeline = _skill(
        name="pipeline",
        skill_id="pipeline-id",
        sub_skills=["extractor-id", "validator-id"],
        agent_type="sequential",
        instructions="",  # SequentialAgent has no instruction
    )
    lookup = {"extractor-id": extractor, "validator-id": validator}
    with patch("adk.agent.get_skill", side_effect=lambda sid: lookup.get(sid)):
        agent = create_agent(pipeline, _user())
    assert isinstance(agent, SequentialAgent)
    assert not isinstance(agent, LlmAgent)
    assert len(agent.sub_agents) == 2
    assert agent.sub_agents[0].name == _safe_agent_name("extractor-id")
    assert agent.sub_agents[1].name == _safe_agent_name("validator-id")


def test_create_agent_sequential_preserves_subskill_order():
    """SequentialAgent walks sub_agents in declaration order — order matters."""
    from google.adk.agents import SequentialAgent

    a = _skill(name="a", skill_id="a-id")
    b = _skill(name="b", skill_id="b-id")
    c = _skill(name="c", skill_id="c-id")
    # Declare in reverse alphabetical to confirm we preserve subSkills order,
    # not e.g. dict iteration order.
    pipeline = _skill(
        name="p",
        skill_id="p-id",
        sub_skills=["c-id", "a-id", "b-id"],
        agent_type="sequential",
    )
    lookup = {"a-id": a, "b-id": b, "c-id": c}
    with patch("adk.agent.get_skill", side_effect=lambda sid: lookup.get(sid)):
        agent = create_agent(pipeline, _user())
    assert isinstance(agent, SequentialAgent)
    names = [sa.name for sa in agent.sub_agents]
    assert names == [_safe_agent_name("c-id"), _safe_agent_name("a-id"), _safe_agent_name("b-id")]


def test_create_agent_llm_unaffected_by_sequential_branch():
    """The default agent_type='llm' path still returns LlmAgent — no regression."""
    agent = create_agent(_skill(), _user())
    assert isinstance(agent, LlmAgent)


def _ctx(state):
    """Minimal CallbackContext stand-in for callback unit tests.

    ADK passes a CallbackContext with a `state` attribute; the callbacks
    here only read `.state` via `getattr`, so a SimpleNamespace suffices
    without importing ADK's full context object.
    """
    import types as _types

    return _types.SimpleNamespace(state=state)


def test_intake_gate_returns_friendly_content_when_no_document():
    """before_agent_callback returns types.Content when session lacks docs.

    Mirrors ADK BaseAgent._handle_before_agent_callback contract: returning
    Content short-circuits the agent run and that Content becomes the reply.
    """
    from adk.agent import _make_intake_gate

    gate = _make_intake_gate("pipeline-id")
    result = gate(_ctx({"app:docs_loaded": []}))
    assert result is not None
    # ADK contract: must be types.Content with at least one Part containing text
    assert result.role == "model"
    assert any("upload" in (p.text or "").lower() for p in result.parts)


def test_intake_gate_returns_friendly_content_when_state_missing_key():
    """Missing `app:docs_loaded` key is the same as empty — short-circuit."""
    from adk.agent import _make_intake_gate

    gate = _make_intake_gate("pipeline-id")
    assert gate(_ctx({})) is not None


def test_intake_gate_no_op_when_documents_loaded():
    """Documents present → return None → let the pipeline run normally."""
    from adk.agent import _make_intake_gate

    gate = _make_intake_gate("pipeline-id")
    assert gate(_ctx({"app:docs_loaded": ["doc-1"]})) is None


def test_intake_gate_no_op_when_state_is_none():
    """No state → fail open (return None). The rest of the chain handles missing state."""
    from adk.agent import _make_intake_gate

    gate = _make_intake_gate("pipeline-id")
    assert gate(_ctx(None)) is None


def test_final_progress_callback_returns_none_and_does_not_raise():
    """after_agent_callback is fire-and-forget — must never raise.

    The callback marks a STAGE_PROGRESS event on the LatencyTracker. When no
    tracker is active (e.g. unit-test context), get_current_tracker returns
    a NullLatencyTracker whose mark() is a no-op. Either way the callback
    returns None and propagates no exceptions to the runtime.
    """
    from adk.agent import _make_final_progress

    cb = _make_final_progress("pipeline-id")
    assert cb(_ctx({})) is None  # the public contract


def test_create_agent_sequential_wires_intake_gate_and_final_progress():
    """SequentialAgent wraps the two callbacks built by the M1 helpers."""
    from google.adk.agents import SequentialAgent

    pipeline = _skill(name="pipeline", skill_id="pipeline-id", agent_type="sequential")
    agent = create_agent(pipeline, _user())
    assert isinstance(agent, SequentialAgent)
    # Both callbacks attached; ADK stores them as Optional[Callable | list[Callable]]
    assert agent.before_agent_callback is not None
    assert agent.after_agent_callback is not None


# --- WORKFLOW-PIPELINE M4: per-specialist STAGE_PROGRESS labels ---


def test_emit_specialist_stage_label_recognises_three_ap_specialists():
    """Each AP specialist has a STAGE_PROGRESS label keyed by SKILL.md name.

    Lookup is by `name` (stable across re-seeds), not skill_id (which is
    a fresh UUID per Firestore environment).
    """
    from adk.agent import _AP_SPECIALIST_STAGE_LABELS

    for name in ("invoice-extractor", "ap-validator", "ap-poster"):
        assert name in _AP_SPECIALIST_STAGE_LABELS, f"missing label for {name!r}"
        stage, label = _AP_SPECIALIST_STAGE_LABELS[name]
        assert stage.startswith("ap_stage_"), f"stage name {stage!r} should be namespaced"
        assert label and label[-1] in "…", f"label {label!r} should end with ellipsis"


def test_emit_specialist_stage_label_calls_tracker_for_known_specialist():
    """Known AP specialist → tracker.mark fires with the correct label.

    Other skills (e.g. the orchestrator, generic chat skills) must NOT
    emit one of these labels — they belong to the pipeline narrative only.
    """
    from unittest.mock import MagicMock

    from adk.agent import _emit_specialist_stage_label

    mock_tracker = MagicMock()
    with patch("observability.timing.get_current_tracker", return_value=mock_tracker):
        _emit_specialist_stage_label("invoice-extractor")
    mock_tracker.mark.assert_called_once_with("ap_stage_extract", user_label="Extracting invoice fields…")


def test_emit_specialist_stage_label_no_op_for_unknown_skill():
    """Unknown skill names (orchestrator, generic skills) → no mark call.

    The labels are AP-specialist-only — emitting them for the orchestrator
    or a generic chat skill would pollute the typing indicator with
    misleading 'Extracting…' text.
    """
    from unittest.mock import MagicMock

    from adk.agent import _emit_specialist_stage_label

    mock_tracker = MagicMock()
    with patch("observability.timing.get_current_tracker", return_value=mock_tracker):
        _emit_specialist_stage_label("ap-orchestrator")
        _emit_specialist_stage_label("general-assistant")
        _emit_specialist_stage_label("ap-pipeline")  # the SequentialAgent itself, not a specialist
    mock_tracker.mark.assert_not_called()


def test_emit_specialist_stage_label_swallows_tracker_failure():
    """Instrumentation must never break the chat path — a tracker exception
    is logged and swallowed."""
    from adk.agent import _emit_specialist_stage_label

    def _boom(*_a, **_kw):
        raise RuntimeError("tracker exploded")

    with patch("observability.timing.get_current_tracker", side_effect=_boom):
        # Must not raise
        _emit_specialist_stage_label("invoice-extractor")
