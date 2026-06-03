"""ADK Agent factory — creates agents from SkillConfig documents.

Workshop W2b — ADK: The Foundation (factory)
  `create_agent()` reads a SkillConfig from Firestore and assembles an
  LlmAgent. The three-line model router (Gemini / Claude / LiteLlm) and
  the `_HeuristicRouter` thinking-tier are the moments to linger on during
  the talk — they show what ADK's model abstraction buys you.

The factory has three layers:
  1. `resolve_model(model_id)` — maps a skill's model string to the correct
     ADK model wrapper (Gemini / Claude / LiteLlm).
  2. `resolve_tools(...)` — from `adk.tools` — wraps callables as
     FunctionTool instances for the agent.
  3. `create_agent(skill_config, user)` and `create_agent_with_thinking(...)`
     — assemble the above into an ADK LlmAgent with per-user callbacks.

Thinking strategy (3 tiers, see docs/design/v6.0.0/agent-factory.md):
  A. Gemini only, no `thinking_model` → single agent with
     `BuiltInPlanner(thinking_budget=-1)` (Gemini 2.5 dynamic thinking).
  B. Claude/OpenAI, no `thinking_model` → single agent, no planner.
  C. Any provider, `thinking_model` set → `_HeuristicRouter(fast, thinking,
     picker)` that picks between two agents via `_should_think(message)`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.models import Claude, Gemini
from google.adk.models.lite_llm import LiteLlm
from google.adk.planners import BuiltInPlanner
from google.adk.tools import AgentTool
from google.adk.tools.load_artifacts_tool import load_artifacts_tool
from google.adk.tools.load_memory_tool import load_memory_tool
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.genai import types as genai_types
from google.genai.types import ThinkingConfig

from adk.a2ui import A2uiToolConfig, make_a2ui_toolset
from adk.a2ui_surface_context import wrap_with_a2ui_surface_context
from adk.artifact_tools import retrieve_artifact
from adk.callbacks import (
    _handle_large_output,
    make_after_agent_response,
    make_before_agent,
    make_document_injector,
    make_document_loader,
    make_permission_enforcer,
    make_session_tracker,
)
from adk.iframe_context import wrap_with_iframe_context
from adk.instruction_provider_chain import compose_instruction_providers
from adk.mcp_observability import (
    compose_after_tool_callbacks,
    compose_before_tool_callbacks,
    make_mcp_after_tool_callback,
    make_mcp_before_tool_callback,
)
from adk.tools import resolve_mcp_tools, resolve_tools
from auth.access_context import AccessContext
from auth.firebase_auth import User
from db.models import SkillConfig
from skills.skill_config import find_by_name, get_skill
from tools.schemas import resolve_schema_ref
from tools.structured_extraction import structured_extraction_callback

logger = logging.getLogger(__name__)


# --- Model routing ---


def resolve_model(model_id: str) -> Gemini | Claude | LiteLlm:
    """Create the correct ADK model wrapper for the given model ID.

    - `gemini-*` -> `Gemini(model=...)` (Vertex AI via ADC)
    - `claude-*` -> `Claude(model=...)` (Vertex AI Anthropic models)
    - `gpt-*` / `o3*` -> `LiteLlm(model="openai/...")` (requires OPENAI_API_KEY)

    Raises:
        ValueError: If the model_id does not match a known provider prefix.
    """
    if model_id.startswith("gemini-"):
        return Gemini(model=model_id)
    if model_id.startswith("claude-"):
        return Claude(model=model_id)
    if model_id.startswith("gpt-") or model_id.startswith("o3"):
        return LiteLlm(model=f"openai/{model_id}")
    raise ValueError(f"Unsupported model: {model_id!r}")


# --- Name sanitisation ---
# ADK's LlmAgent name validator requires `^[a-zA-Z_][a-zA-Z0-9_]*$`. Skill
# IDs default to UUIDs (contain hyphens) and may start with a digit; kebab-
# case names also have hyphens. Sanitize once at the factory boundary.

_VALID_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _safe_agent_name(skill_id: str) -> str:
    safe = skill_id.replace("-", "_")
    if not safe:
        return "s_"
    if not (safe[0].isalpha() or safe[0] == "_"):
        safe = "s_" + safe
    if not _VALID_IDENT.match(safe):
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", safe)
    return safe


# --- Thinking strategy ---

# Keywords that suggest a user message warrants deeper reasoning. Kept short
# and boring on purpose: false positives route to the better model, the cost
# of being wrong is a few extra tokens — we prefer a high recall heuristic.
THINK_KEYWORDS = frozenset(
    {
        "analyze",
        "analyse",
        "reason",
        "compare",
        "evaluate",
        "plan",
        "design",
        "debug",
        "explain",
        "derive",
        "prove",
    }
)


def _should_think(message: str) -> bool:
    """Heuristic: does this message warrant the thinking model?

    Rules (any one triggers thinking):
      - length > 280 chars (beyond a typical one-liner)
      - contains any THINK_KEYWORDS word
      - has >=2 question marks (compound / multi-part question)
    """
    if len(message) > 280:
        return True
    if message.count("?") >= 2:
        return True
    tokens = {t.strip(".,!?:;").lower() for t in message.split()}
    return bool(tokens & THINK_KEYWORDS)


def _planner_for(skill_config: SkillConfig) -> BuiltInPlanner | None:
    """Return a BuiltInPlanner for Gemini skills with no thinking_model.

    - Gemini + no thinking_model: `BuiltInPlanner(thinking_budget=-1)` —
      Gemini 2.5's dynamic thinking (the model decides per request).
    - Claude / OpenAI: BuiltInPlanner is Gemini-specific; return None.
    - thinking_model set: routing happens in Python via _HeuristicRouter;
      the single-agent case doesn't apply, so return None here.
    """
    if skill_config.skill_metadata.thinking_model is not None:
        return None
    if not skill_config.skill_metadata.model.startswith("gemini-"):
        return None
    return BuiltInPlanner(thinking_config=ThinkingConfig(thinking_budget=-1))


@dataclass
class _HeuristicRouter:
    """Wraps two agents (`fast` and `thinking`) and a picker heuristic.

    Not itself an ADK Agent — the SSE endpoint calls `pick_agent(message)`
    to choose which agent to hand to the Runner for a given turn.
    """

    fast: LlmAgent
    thinking: LlmAgent
    picker: Callable[[str], bool]

    def pick_agent(self, message: str) -> LlmAgent:
        return self.thinking if self.picker(message) else self.fast


# --- Model-aware search tool wiring ---


def _resolve_search_tools(
    tool_names: list[str],
    tool_configs: dict,
) -> list:
    """Return search AgentTools for a skill — one or two sub-agents as needed.

    All models (Gemini, Claude, OpenAI) use the sub-agent pattern so the root
    agent never has grounding built-ins alongside FunctionTools (400 INVALID_ARGUMENT).
    ADK tracks this as TODO(b/448114567) and will remove the workaround when fixed upstream.

    google_search and VertexAiSearchTool use incompatible API-level tool types
    (google_search vs retrieval) and cannot share an agent, so each gets its own:
      - google_search → GoogleSearchAgentTool (ADK-native, propagates grounding metadata)
      - ai_search     → AgentTool(enterprise_search_agent, propagate_grounding_metadata=True)
      - both          → two AgentTools, both returned
    """
    from google.adk.tools.google_search_agent_tool import GoogleSearchAgentTool

    from tools.search_agent import create_enterprise_search_agent, create_web_search_agent

    wants_web = "google_search" in tool_names
    wants_enterprise = "ai_search" in tool_names

    if not (wants_web or wants_enterprise):
        return []

    result = []
    if wants_web:
        result.append(GoogleSearchAgentTool(create_web_search_agent()))
    if wants_enterprise:
        datastore_id: str | None = (tool_configs.get("ai_search") or {}).get("datastore_id")
        if datastore_id:
            result.append(AgentTool(create_enterprise_search_agent(datastore_id), propagate_grounding_metadata=True))
        else:
            logger.warning("ai_search tool requested but no datastore_id in tool_configs; skipping enterprise search")
    return result


def _resolve_code_executor(
    tool_names: list[str],
    model_id: str,
) -> tuple[BuiltInCodeExecutor | None, list]:
    """Return (code_executor, extra_tools) for a skill's code execution needs.

    Gemini agents: BuiltInCodeExecutor attached directly to the LlmAgent.
    Claude/OpenAI agents: AgentTool wrapping a Gemini CodeAgent sub-agent.

    Returns:
        (executor, tools) — executor is None when model is non-Gemini or no
        code_execution tool requested; tools is empty for Gemini agents.
    """
    if "code_execution" not in tool_names:
        return None, []

    if model_id.startswith("gemini-"):
        return BuiltInCodeExecutor(), []

    from tools.code_execution.agent import create_code_agent

    return None, [AgentTool(create_code_agent())]


# --- Agent factory ---


def _resolve_extraction_schema_for_skill(skill_config: SkillConfig) -> dict | None:
    """Resolve `metadata.extraction_schema` (named ref or inline) to a dict.

    SCHEMA-ENFORCE sprint: called once at agent build time for each skill.
    Unknown named references log a warning and resolve to None — the skill
    still works, the after-agent extraction step just no-ops on that run.
    Lets a fork ship a typo'd SKILL.md without taking the whole agent down.
    """
    value = skill_config.skill_metadata.extraction_schema if skill_config.skill_metadata else None
    if value is None:
        return None
    try:
        return resolve_schema_ref(value)
    except ValueError as exc:
        logger.warning(
            "schema-enforce: skill=%s extraction_schema=%r unresolved (%s); "
            "extraction will no-op for this skill until SKILL.md is corrected",
            skill_config.skill_id,
            value,
            exc,
        )
        return None


def _set_extraction_schema_in_state(callback_context: object, schema: dict | None) -> None:
    """Before-agent callback: write the resolved schema into session state.

    The structured_extraction_callback (existing, fires after every agent
    run) reads from app:extraction_schema and runs Gemini's constrained
    decoding when present. Writing here means each agent's run starts with
    the right schema in state — sub-agents transferred to inherit it
    automatically, and skills without an extraction_schema land None
    (the callback treats falsy as "no enforcement").
    """
    state = getattr(callback_context, "state", None)
    if state is None:
        return
    # Always assign — schema=None overrides any inherited value from a
    # previous skill in the same session (defensive: prevents the
    # invoice-extractor's ap_invoice from leaking into the orchestrator's
    # response when the orchestrator runs without its own schema).
    state["app:extraction_schema"] = schema


# --- WORKFLOW-PIPELINE M1: SequentialAgent wiring ---


_INTAKE_GATE_MESSAGE = (
    "Please upload or select an invoice document, then ask me to process it. "
    "I run a deterministic Extract → Validate → Post pipeline and need a "
    "document to work from."
)


def _make_intake_gate(skill_id: str) -> Callable:
    """Build a before_agent_callback that blocks the pipeline when no doc is in state.

    SequentialAgent inherits BaseAgent's contract: a before_agent_callback
    returning ``types.Content`` short-circuits the agent run and the Content
    becomes the final reply (see google.adk.agents.base_agent.BaseAgent._handle_before_agent_callback).
    Returning None lets the workflow continue normally.

    The state key matches `adk.callbacks._STATE_DOCS_LOADED` ("app:docs_loaded")
    — set by the document loader at the orchestrator level, inherited by
    sub-agent invocations within the same session.
    """

    def intake_gate(callback_context: object) -> genai_types.Content | None:
        state = getattr(callback_context, "state", None)
        if state is None:
            # Without state we can't tell — let the pipeline try. Same fail-open
            # posture as the rest of the callback chain.
            return None
        loaded = state.get("app:docs_loaded") or []
        if loaded:
            return None
        logger.info(
            "workflow_pipeline.intake_gate: skill=%s no document loaded, short-circuiting",
            skill_id,
        )
        return genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=_INTAKE_GATE_MESSAGE)],
        )

    return intake_gate


def _make_final_progress(skill_id: str) -> Callable:
    """Build an after_agent_callback that emits one closing STAGE_PROGRESS event.

    The user-facing typing indicator clears as soon as the final A2UI surface
    lands, but the closing label is useful in Cloud Trace + telemetry for
    drawing a clean per-pipeline span. Fail-open: tracking failures must
    never break the chat path.
    """

    def final_progress(callback_context: object) -> None:
        try:
            from observability.timing import get_current_tracker

            get_current_tracker().mark("pipeline_done", user_label="Done — invoice processed")
        except Exception as exc:
            logger.warning(
                "workflow_pipeline.final_progress: skill=%s tracker mark failed (suppressed): %s",
                skill_id,
                exc,
            )
        return None

    return final_progress


def _build_sequential_agent(
    skill_config: SkillConfig,
    user: User,
    *,
    access_context: AccessContext | None,
    _seen: set[str],
) -> SequentialAgent:
    """Build a deterministic SequentialAgent that walks sub_skills in order.

    Mirrors create_agent's sub-skill resolution loop (skill_id-or-name lookup
    via get_skill / find_by_name) so a SequentialAgent and a sub-skill-using
    LlmAgent both resolve their children the same way. Cycle detection is
    inherited from the caller via _seen.
    """
    md = skill_config.skill_metadata
    sub_agents: list = []
    for sub_id in md.sub_skills:
        sub = get_skill(sub_id) or find_by_name(sub_id)
        if sub is None:
            logger.warning(
                "sub-skill %r referenced by sequential agent %r not found; skipping",
                sub_id,
                skill_config.skill_id,
            )
            continue
        sub_agents.append(create_agent(sub, user, access_context=access_context, _seen=_seen))

    return SequentialAgent(
        name=_safe_agent_name(skill_config.skill_id),
        description=skill_config.description or "",
        sub_agents=sub_agents,
        before_agent_callback=_make_intake_gate(skill_config.skill_id),
        after_agent_callback=_make_final_progress(skill_config.skill_id),
    )


def create_agent(
    skill_config: SkillConfig,
    user: User,
    *,
    access_context: AccessContext | None = None,
    _seen: set[str] | None = None,
    _model_override: str | None = None,
    _planner_override: BuiltInPlanner | None = None,
) -> LlmAgent:
    """Build an ADK LlmAgent from a SkillConfig + authenticated User.

    - `name` = sanitized `skill_id` (ADK rejects hyphens)
    - `instruction` = `skill_config.instructions` (Agent Skills spec field)
    - `tools` resolved from `skill_metadata.tools` (unknowns skipped+logged)
    - `sub_agents` recursed from `skill_metadata.sub_skills` (skill IDs
      looked up via `skills.skill_config.get_skill`); cycle-detected via
      the private `_seen` set.
    - `before_tool_callback` = `make_permission_enforcer(user.email, user.domain)`

    Args:
        _seen: internal. Set of skill IDs already on the current call stack,
            used to detect cycles. Callers should leave as None.
        _model_override: internal. When building router sub-agents,
            _create_router_sub_agent uses this to swap the model without
            duplicating the recursion logic.
        _planner_override: internal. Same deal for the planner — None means
            "use _planner_for(skill_config)".

    Raises:
        ValueError: if a sub-skill cycle is detected.
    """
    seen = set(_seen) if _seen else set()
    if skill_config.skill_id in seen:
        raise ValueError(
            f"Sub-skill cycle detected: {skill_config.skill_id!r} already on the resolution stack {seen!r}"
        )
    seen.add(skill_config.skill_id)

    md = skill_config.skill_metadata

    # WORKFLOW-PIPELINE M1: deterministic workflow agents short-circuit here.
    # `agent_type == "sequential"` builds an ADK SequentialAgent that walks
    # sub_skills in order — no model, no tools, no LLM at the workflow level.
    # Used by ap-pipeline; defaults preserve LlmAgent behaviour for every
    # other skill.
    if md.agent_type == "sequential":
        return _build_sequential_agent(skill_config, user, access_context=access_context, _seen=seen)

    effective_model = _model_override or md.model
    model = resolve_model(effective_model)
    # Default tools every skill gets (opt-out via toolConfigs.defaults in SKILL.md):
    #   load_artifacts_tool  - LLM-driven artifact retrieval (legacy path; the
    #                          before_model_callback in callbacks.py also
    #                          eager-injects docs on resumed sessions).
    #   retrieve_artifact    - keyword/section search inside a known artifact.
    #   load_memory_tool     - LLM-driven semantic search over the Vertex
    #                          memory bank. Required for cross-session recall.
    #   preload_memory_tool  - auto-fetches relevant memories before the LLM
    #                          turn (same memory bank). Pairs with
    #                          load_memory_tool: preload primes context,
    #                          load_memory follows up for deeper queries.
    _defaults_cfg = md.tool_configs.get("defaults", {}) if isinstance(md.tool_configs, dict) else {}
    tools = [
        *([load_artifacts_tool, retrieve_artifact] if _defaults_cfg.get("artifacts", True) else []),
        *([load_memory_tool, preload_memory_tool] if _defaults_cfg.get("memory", True) else []),
        *resolve_tools(md.tools, md.tool_configs),
    ]
    tools.extend(_resolve_search_tools(md.tools, md.tool_configs))
    tools.extend(resolve_mcp_tools(md.tool_configs))
    # MULTI-SURFACE-A2UI M1 — read the skill's `tool_configs.a2ui` block so
    # the toolset emits `surface_id`/`update_mode` siblings alongside
    # `validated_a2ui_json`. Defaults (no a2ui block) preserve pre-M1
    # inline-in-chat behaviour. Invalid combinations (e.g. patch+chat)
    # raise here at agent-build time, not at the first tool call.
    a2ui_cfg = A2uiToolConfig.from_tool_configs(md.tool_configs)
    if a2ui_cfg.enabled:
        tools.append(make_a2ui_toolset(config=a2ui_cfg))
    code_executor, code_tools = _resolve_code_executor(md.tools, effective_model)
    tools.extend(code_tools)
    planner = _planner_override if _planner_override is not None else _planner_for(skill_config)

    sub_agents: list[LlmAgent] = []
    for sub_id in md.sub_skills:
        # subSkills may reference a sub-skill by its Firestore skill_id OR,
        # for hand-authored templates that can't know generated ids, by its
        # name. Try id first, then fall back to a name lookup.
        sub = get_skill(sub_id) or find_by_name(sub_id)
        if sub is None:
            logger.warning(
                "sub-skill %r referenced by %r not found; skipping",
                sub_id,
                skill_config.skill_id,
            )
            continue
        sub_agents.append(create_agent(sub, user, access_context=access_context, _seen=seen))

    _before_agent = make_before_agent(
        skill_config.skill_id,
        tool_configs=md.tool_configs,
        access_context=access_context,
    )
    _session_tracker = make_session_tracker(user.uid, skill_config.skill_id)
    _document_loader = make_document_loader()
    _document_injector = make_document_injector()
    # SCHEMA-ENFORCE: resolve metadata.extraction_schema (name or inline dict)
    # once at agent build time and write into session state on every run start.
    # When None, the structured_extraction_callback after-agent step no-ops.
    _resolved_extraction_schema = _resolve_extraction_schema_for_skill(skill_config)

    async def _composed_before_agent(callback_context: object) -> None:
        # TTFT mark: ADK has finished its runner setup and is now invoking
        # our before_agent_callback. The gap from agent_factory_done →
        # runner_setup_done attributes ag_ui_adk wrap + ADK runner enter
        # + plugin setup — the second-largest unexplained cost the M1
        # baseline revealed. See docs/design/v6.1.0/ttft-optimization.md.
        from observability.timing import STAGE_RUNNER_SETUP_DONE, get_current_tracker

        get_current_tracker().mark(STAGE_RUNNER_SETUP_DONE)

        _before_agent(callback_context)
        _session_tracker(callback_context)
        _set_extraction_schema_in_state(callback_context, _resolved_extraction_schema)
        await _document_loader(callback_context)

        # TTFT: mark the end of the synchronous before-agent chain. Show
        # a user-facing "Reading documents…" label only when the loader
        # actually loaded something (avoids flashing the label for 0ms
        # on chats with no docs attached).
        from adk.callbacks import _STATE_DOCS_LOADED
        from observability.timing import (
            STAGE_BEFORE_AGENT_DONE,
            get_current_tracker,
        )

        state = getattr(callback_context, "state", None)
        loaded = list(state.get(_STATE_DOCS_LOADED) or []) if state is not None else []
        label: str | None = None
        if loaded:
            suffix = "s" if len(loaded) != 1 else ""
            label = f"Reading {len(loaded)} document{suffix}…"
        get_current_tracker().mark(STAGE_BEFORE_AGENT_DONE, user_label=label)

    _after_agent_response = make_after_agent_response()

    async def _composed_after_agent(callback_context: object) -> None:
        _after_agent_response(callback_context)
        await structured_extraction_callback(callback_context)

    # Sprint 2.12 (M2): pluggable budget enforcement. The before/after
    # model callback pair consults the registered enforcer pre-call,
    # raises BudgetExceededError on hard block (caught by AG-UI's
    # error translator), and reconciles the held projection with
    # realised usage post-call. No-ops when no enforcer is registered
    # OR the skill has no `tool_configs.budget` block — back-compat
    # with every existing skill.
    from adk.budget_config import BudgetConfig
    from budget import get_registered_enforcer
    from budget.callback import make_budget_callbacks

    _budget_before, _budget_after = make_budget_callbacks(
        get_registered_enforcer(),
        user=user,
        skill_id=skill_config.skill_id,
        budget_config=BudgetConfig.from_tool_configs(md.tool_configs),
    )

    async def _composed_before_model(callback_context: object, llm_request: object) -> None:
        # Document injector runs FIRST so docs are visible to the
        # budget projection (longer prompt = higher projected cost).
        # The injector predates the budget gate; if dropping a
        # participant here, see test_composed_before_model.py.
        await _document_injector(callback_context, llm_request)
        await _budget_before(callback_context, llm_request)

    async def _composed_after_model(callback_context: object, llm_response: object) -> None:
        await _budget_after(callback_context, llm_response)

    # M2B-BACKEND (MCP-APP-INTEGRATIONS): tag OTel spans on every MCP tool
    # call with mcp_app.server_id, and mcp_app.has_ui_resource=true when the
    # tool returned an EmbeddedResource carrying a UI app. Composed AFTER the
    # existing callbacks so permission-enforcer / large-output handlers keep
    # their override semantics; observability is purely additive.
    _before_tool = compose_before_tool_callbacks(
        make_permission_enforcer(user.email, user.domain),
        make_mcp_before_tool_callback(),
    )
    _after_tool = compose_after_tool_callbacks(
        _handle_large_output,
        make_mcp_after_tool_callback(),
    )

    return LlmAgent(
        name=_safe_agent_name(skill_config.skill_id),
        model=model,
        # Chained InstructionProviders, applied LEFT-TO-RIGHT — each
        # wrapper's prompt block is appended in the order listed:
        #   * iframe-context (sprint 1.25): mcp_app_context.* block when
        #     an MCP App iframe pushed `ui/update-model-context`.
        #   * A2UI surface-context (sprint 2.10): a2ui_surface_context
        #     block when frontend SurfaceModels have active data OR a
        #     user dispatched an A2uiClientAction.
        # Each wrapper passes through unchanged when its respective
        # state is empty, so this is safe to apply unconditionally
        # for every skill. Adding a third wrapper later is just a
        # third argument here — no nesting to re-order.
        instruction=compose_instruction_providers(
            skill_config.instructions,
            wrap_with_iframe_context,
            wrap_with_a2ui_surface_context,
        ),
        description=skill_config.description,
        tools=tools,
        sub_agents=sub_agents,
        planner=planner,
        code_executor=code_executor,
        before_agent_callback=_composed_before_agent,
        before_model_callback=_composed_before_model,
        after_agent_callback=_composed_after_agent,
        after_model_callback=_composed_after_model,
        before_tool_callback=_before_tool,
        after_tool_callback=_after_tool,
    )


def create_agent_with_thinking(
    skill_config: SkillConfig,
    user: User,
    *,
    access_context: AccessContext | None = None,
) -> LlmAgent | _HeuristicRouter:
    """Dispatch to the three-tier thinking strategy.

    - thinking_model unset → single `create_agent(...)` (planner may be
      attached for Gemini via `_planner_for`).
    - thinking_model set → two agents built (fast from `metadata.model`,
      thinking from `metadata.thinking_model`), wrapped in `_HeuristicRouter`.

    See module docstring for the three tiers in full.
    """
    md = skill_config.skill_metadata
    if md.thinking_model is None:
        return create_agent(skill_config, user, access_context=access_context)

    # Tier 3: two agents + picker. Build both via the same recursive factory
    # so sub-skills/tools/callbacks stay wired identically.
    fast = create_agent(skill_config, user, access_context=access_context)
    thinking = create_agent(
        skill_config,
        user,
        access_context=access_context,
        _model_override=md.thinking_model,
        _planner_override=None,
    )
    return _HeuristicRouter(fast=fast, thinking=thinking, picker=_should_think)
