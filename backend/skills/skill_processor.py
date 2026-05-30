"""Skill request processor — orchestrates a single user turn.

Replaces v5's `process_assistant_request()` with an ADK-native flow:

  1. Look up the skill config; 404 if missing *or* not visible to the caller
     (existence leak prevented).
  2. Build a per-user LlmAgent via `adk.agent.create_agent_with_thinking`.
     The heuristic router picks `fast` vs `thinking` from the user message.
  3. Wrap the agent with `ag_ui_adk.ADKAgent`, using the shared singleton
     session service from `adk.session.get_session_service()` so sessions
     persist across requests within the same process.
  4. Construct an AG-UI `RunAgentInput` and yield each translated event
     as a dict.

Deliberately kept thin — the SSE endpoint owns auth, response shaping,
and header handling; this module just produces the event stream.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from ag_ui.core import RunAgentInput, UserMessage
from google.genai.errors import ClientError

from adk.agent import _HeuristicRouter, create_agent_with_thinking
from adk.agui import build_agui_adk_agent, stream_agui_events
from adk.session import get_session_service
from auth.access_context import AccessContext
from auth.firebase_auth import User
from budget import BudgetExceededError
from skills.skill_config import get_skill

logger = logging.getLogger(__name__)

_session_service = get_session_service()


class SkillNotFoundError(Exception):
    """Raised when a skill is missing OR not visible to the caller.

    The streaming endpoint collapses both cases into a 404 to avoid
    leaking skill existence to users who cannot see them.
    """

    def __init__(self, skill_id: str) -> None:
        super().__init__(f"Skill not found: {skill_id!r}")
        self.skill_id = skill_id


async def process_skill_request(
    skill_id: str,
    user: User,
    access: AccessContext,
    session_id: str | None,
    message: str,
    attachments: list[dict[str, Any]] | None = None,
    document_ids: list[str] | None = None,
    resumed_session: bool = False,
    a2ui_surface_state: dict[str, Any] | None = None,
) -> AsyncGenerator[dict, None]:
    """Yield AG-UI events for one turn of `skill_id`.

    Args:
        skill_id: The skill to invoke.
        user: Authenticated caller (used for permission closures).
        access: Per-request access context for the skill-visibility check.
        session_id: Existing thread ID to resume, or None to start fresh.
        message: The user's message for this turn.
        attachments: Optional attachment metadata (not used in v6.0;
            reserved for v6.1).
        document_ids: Optional Firestore document IDs the user wants in
            context for this turn. The before_agent_callback loads each
            document's blocks as a separate session artifact so the AI
            can read all of them. Re-sending the same ids next turn is
            cheap — the loader skips ids it has already loaded.
        resumed_session: True when the user reached this chat by clicking
            a conversation thread from the per-document Conversations
            panel. Triggers eager doc injection in the LLM request so
            the agent doesn't have to discover the doc via
            ``load_artifacts``. Fresh chats stay on the standard flow.
        a2ui_surface_state: Optional per-turn snapshot of every active
            A2UI surface's data model, as captured by the frontend's
            ``readA2uiSurfaceState`` helper at sendMessage time. Shape:
            ``{surfaceId: {catalogId, dataModel}}``. Seeded into
            ``initial_state["a2ui_surface_state"]`` so the
            ``wrap_with_a2ui_surface_context`` InstructionProvider can
            inject it into the agent's prompt. None when no surfaces
            are active (the common case before any A2UI render).

    Raises:
        SkillNotFoundError: when the skill is missing or not readable.
    """
    skill = get_skill(skill_id)
    if skill is None or not access.can_access_skill(skill):
        raise SkillNotFoundError(skill_id)

    # B1 (chat-history-fixes v6.1.0): synchronously create the session-index
    # row in Firestore *before* the SSE stream opens. The previous home for
    # this write was the ADK before_agent_callback, which fires inside the
    # async agent run — so a user reload between POST returning and the
    # callback completing 404'd on GET /api/sessions/{id}. Doing it here
    # closes the race window. The callback is now idempotent: it observes
    # the existing row and short-circuits.
    thread_id = session_id or f"thread-{uuid.uuid4().hex[:12]}"
    _ensure_session_index(thread_id, skill_id, user.uid, document_ids)

    agent_or_router = create_agent_with_thinking(skill, user)
    if isinstance(agent_or_router, _HeuristicRouter):
        agent = agent_or_router.pick_agent(message)
        routing_choice = "thinking" if agent is agent_or_router.thinking else "fast"
        logger.info("skill=%s routing=%s", skill_id, routing_choice)
    else:
        agent = agent_or_router
        routing_choice = "single"

    # Stash the resolved model + routing on the per-request LatencyTracker
    # so the structured ttft log line and any LATENCY_REPORT event can
    # surface them. Off mode short-circuits inside set_model.
    from observability.timing import STAGE_AGENT_FACTORY_DONE, get_current_tracker

    # TTFT mark: agent factory has finished. The gap from
    # session_index_done → agent_factory_done isolates pure factory cost
    # (model resolve + tool resolve + sub-agent build + planner) from the
    # downstream ag_ui_adk wrap + ADK runner setup that follows.
    # See docs/design/v6.1.0/ttft-optimization.md M1.
    get_current_tracker().mark(STAGE_AGENT_FACTORY_DONE)

    model_used = ""
    raw_model = getattr(agent, "model", None)
    if isinstance(raw_model, str):
        model_used = raw_model
    elif raw_model is not None:
        model_used = getattr(raw_model, "model", "") or str(raw_model)
    get_current_tracker().set_model(model_used, routing_choice)

    # Thread user.uid through so ag_ui_adk creates the Vertex session under
    # the same uid Firestore stores as owner_uid. Without this, ag_ui_adk's
    # default extractor uses f"thread_user_{thread_id}" — divergence point
    # documented in docs/design/v6.1.0/chat-history-deep-fixes-2.md (1.15).
    agui_agent = build_agui_adk_agent(agent, user_id=user.uid, session_service=_session_service)

    initial_state: dict[str, Any] = {}
    if document_ids:
        # NOTE: bare ``document_ids`` round-trips on the AG-UI wire because
        # ag_ui_adk emits it in STATE_SNAPSHOT. We considered ``temp:`` prefix
        # to suppress the round-trip, but ag_ui_adk applies wire state via
        # ``update_session_state`` → ``append_event`` → ADK's
        # ``_trim_temp_delta_state``, which strips temp keys *before*
        # persistence; ag_ui_adk then re-fetches the session via ``get_session``
        # so the temp value (only on a transient copy) is gone before the
        # runner starts. Temp prefix is for in-invocation callback writes, not
        # wire inputs. The bug is mitigated at the parser layer instead:
        # ``_extract_document_ids`` reads forwardedProps first and ignores the
        # round-tripped state value (see fast_api_app.py:298).
        initial_state["document_ids"] = list(document_ids)
    if resumed_session:
        # Read by make_document_injector — eager-inject loaded docs into
        # the first LLM request of every turn for resumed sessions.
        initial_state["app:resumed_session"] = True
    if a2ui_surface_state:
        # Sprint 2.10 — per-turn snapshot of every active A2UI surface's
        # dataModel + catalogId. The wrap_with_a2ui_surface_context
        # InstructionProvider reads this from ctx.state on the next
        # agent turn and injects the values into the system prompt
        # under the `a2ui_surface_context.{surfaceId}` namespace.
        # Empty/None bypasses (the snapshot is omitted for skills that
        # haven't rendered any A2UI yet — InstructionProvider is a
        # no-op when state has neither this key nor namespaced action
        # writes).
        initial_state["a2ui_surface_state"] = a2ui_surface_state
    run_input = RunAgentInput(
        threadId=thread_id,
        runId=f"run-{uuid.uuid4().hex[:8]}",
        state=initial_state,
        messages=[
            UserMessage(
                id=f"msg-{uuid.uuid4().hex[:8]}",
                role="user",
                content=message,
            )
        ],
        tools=[],
        context=[],
        forwardedProps={},
    )

    try:
        async for event in stream_agui_events(agui_agent, run_input):
            yield event
    except BudgetExceededError as exc:
        # Sprint 2.12 — the budget enforcer's before_model callback
        # refused the turn (cohort over cap). Translate to a typed
        # AG-UI RUN_ERROR carrying the decision's message + retry-after
        # so the frontend BudgetBanner can render a countdown. The
        # `code` field follows the existing VERTEX_AUTH_FAILED pattern;
        # `retry_after_seconds` rides as a passthrough field (the
        # RunErrorEventSchema is passthrough — extras survive).
        decision = exc.decision
        logger.warning(
            "skill=%s budget exceeded: identity_value=opaque retry_after=%ss",
            skill_id,
            decision.retry_after_seconds,
        )
        yield {
            "type": "RUN_ERROR",
            "message": decision.message or "Budget exceeded.",
            "code": "BUDGET_EXCEEDED",
            "retry_after_seconds": decision.retry_after_seconds,
        }
    except ClientError as exc:
        # Vertex AI / Gemini API failures bubble up as ClientError. Translate
        # to an AG-UI RUN_ERROR event so the chat UI can render an actionable
        # banner instead of a frozen stream. The most common cause in dev is
        # ADC quota_project drift surfaced as 401 CREDENTIALS_MISSING.
        message, code = _translate_client_error(exc)
        logger.error("skill=%s upstream API error: %s", skill_id, exc)
        yield {"type": "RUN_ERROR", "message": message, "code": code}


def _ensure_session_index(
    thread_id: str,
    skill_id: str,
    owner_uid: str,
    document_ids: list[str] | None,
) -> None:
    """Synchronously create the chat_sessions/{thread_id} row if absent,
    and ArrayUnion this turn's document_ids onto it whether or not the
    row already existed.

    See B1 in docs/design/v6.1.0/chat-history-fixes.md for the original
    race-fix that motivated the synchronous create. The doc-id ArrayUnion
    on every turn is the "stranded session" fix: a session that lands
    with ``documentIds=[]`` (e.g. user typed before opening a tab, or
    reloaded onto a 404'd session_id) would otherwise stay invisible
    from every per-doc Conversations panel — ``list_sessions_for_document``
    uses Firestore ``array_contains``, which skips empty lists. The
    async loader's own ``add_session_documents`` only fires after a
    successful artifact load and only on flush turns, so depending on
    it leaves a window where the user has clearly attached a doc to
    the chat but the doc panel shows "No conversations yet". Reified
    by ``test_session_index_document_ids_grow_when_doc_added_after_empty_first_turn``.

    Failures are logged and swallowed — the after_agent_callback still
    runs as a fallback flusher.
    """
    from db.chat_sessions import (
        add_session_documents,
        create_session_index,
        get_session_index,
    )

    try:
        existing = get_session_index(thread_id)
    except Exception as exc:
        logger.warning("session-index existence check failed for %s: %s", thread_id, exc)
        return

    docs = list(document_ids) if document_ids else []

    if existing is None:
        anchor_doc_id = docs[0] if docs else None
        access_control = _derive_initial_access_control(anchor_doc_id)
        try:
            create_session_index(
                session_id=thread_id,
                skill_id=skill_id,
                owner_uid=owner_uid,
                access_control=access_control,
                document_ids=docs,
            )
            logger.info("chat_sessions/%s index created synchronously (owner=%s)", thread_id, owner_uid)
        except Exception as exc:
            logger.warning("synchronous session-index write failed for %s: %s", thread_id, exc)
        return

    # Row already exists. ArrayUnion the current turn's docs so a
    # session created with empty docs (turn 1 typed before opening a
    # tab) still shows up under the doc's panel as soon as the user
    # attaches one — without waiting for the async loader's own
    # add_session_documents call which only fires on flush turns.
    if docs:
        try:
            add_session_documents(thread_id, docs)
        except Exception as exc:
            logger.warning(
                "synchronous documentIds union failed for %s: %s",
                thread_id,
                exc,
            )


def _derive_initial_access_control(document_id: str | None):
    """Resolve initial access_control for a new session row from its anchor doc.

    Mirrors ``adk.callbacks._derive_access_control`` but kept local to this
    module to avoid importing private helpers across package boundaries.
    """
    from db.models.access import AccessControl

    if not document_id:
        return AccessControl(type="private")
    try:
        from db.firestore import get_document

        doc = get_document("parsed_documents", document_id)
        if doc and "accessControl" in doc:
            ac_data = doc["accessControl"]
            if isinstance(ac_data, dict):
                return AccessControl.model_validate(ac_data)
    except Exception as exc:
        logger.warning("could not derive access_control for new session: %s", exc)
    return AccessControl(type="private")


def _translate_client_error(exc: ClientError) -> tuple[str, str]:
    """Map a google.genai ClientError to a (user_message, error_code) pair."""
    status = getattr(exc, "code", None)
    raw = str(exc)
    if status == 401 or "CREDENTIALS_MISSING" in raw or "UNAUTHENTICATED" in raw:
        return (
            "Backend can't authenticate to Vertex AI. "
            "Local dev: run `gcloud auth application-default set-quota-project "
            "$GOOGLE_CLOUD_PROJECT` and restart the backend. "
            "Production: confirm the service account has roles/aiplatform.user.",
            "VERTEX_AUTH_FAILED",
        )
    return (f"Upstream API error ({status or '?'}): {raw}", "UPSTREAM_API_ERROR")
