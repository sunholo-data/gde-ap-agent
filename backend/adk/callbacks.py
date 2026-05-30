"""ADK callback hooks for the Aitana platform.

Callbacks wired into every skill by `adk.agent.create_agent`:
  * `before_tool_callback`   = `make_permission_enforcer(email, domain)`
  * `before_agent_callback`  = `make_before_agent(skill_id)` composed with
                               `make_session_tracker(owner_uid)` — the latter
                               creates/initialises the ChatSessionIndex on the
                               first turn of a new session.
  * `after_agent_callback`   = `make_after_agent_response(owner_uid)` — bumps
                               counters in the index and generates a title
                               after turn 2.
  * `after_tool_callback`    = `_handle_large_output`

`make_*` factories capture per-user context in closures to avoid threading
it through ADK session state.

Debounce: turnCount / lastMessageAt are flushed to Firestore every
`_TURN_FLUSH_INTERVAL` turns OR when the title needs to be set — keeps
Firestore QPS low during bursty agent loops.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from opentelemetry import trace

from auth.access_context import AccessContext
from auth.permissions import ToolPermissionDenied, can_use_tool
from db.chat_sessions import add_session_documents, get_session_index
from db.models.access import AccessControl

logger = logging.getLogger(__name__)

# Only flush counter updates every N turns to reduce Firestore write amplification.
_TURN_FLUSH_INTERVAL = 5

# Tool responses larger than this (in characters of their string form) are
# offloaded to an ADK artifact and replaced with a short pointer in the LLM
# context — keeps the agent from paying megabytes of tokens per turn.
_LARGE_OUTPUT_THRESHOLD = 50_000


# --- before_tool_callback ---


def make_permission_enforcer(
    user_email: str,
    user_domain: str,
) -> Any:
    """Return a ``before_tool_callback`` that enforces tool permissions."""

    def _enforcer(
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        tool_name = tool.name
        if not can_use_tool(user_email, user_domain, tool_name):
            logger.info(
                "perm: blocked %s for %s (tool=%s)",
                user_email,
                tool_context.agent_name,
                tool_name,
            )
            raise ToolPermissionDenied(user_email, tool_name)

        # TTFT: emit a STAGE_PROGRESS label per tool call so the UI can
        # show "Calling search…" instead of an indefinite cursor while
        # the model waits on the tool. Each call gets its own mark name
        # (suffixed by a per-turn counter) — same name twice would be
        # idempotent and the second tool's label would never fire.
        from observability.timing import STAGE_TOOL_CALL_STARTED, get_current_tracker

        tracker = get_current_tracker()
        tracker.mark(
            f"{STAGE_TOOL_CALL_STARTED}_{tracker.tools_invoked_count}",
            user_label=f"Calling {tool_name}…",
        )

        return None

    return _enforcer


# --- before_agent_callback ---


def make_before_agent(
    skill_id: str,
    tool_configs: dict[str, Any] | None = None,
    access_context: AccessContext | None = None,
) -> Any:
    """Return a ``before_agent_callback`` that:

    1. Annotates the current OTEL span with the original (pre-sanitization)
       ``skill_id`` and, if the SSE endpoint has set ``routing_choice`` on
       session state, that too.
    2. (RESOURCE-ACCESS M3) If ``tool_configs`` + ``access_context`` are
       provided, resolves any ``bucket_folders`` entries to signed URLs and
       stashes them under ``callback_context.state['signed_urls']``.
       Downstream tools then read URLs from state instead of re-hitting
       Firestore on every turn.

    Captures ``skill_id`` in a closure so we keep the original kebab-case /
    UUID form rather than the sanitized agent name.

    tool_configs shape (convention for M3):
        {"<tool_name>": {"bucket_folders": [{"bucket_id": "...", "folder_id": "..."}]}}
    TODO(v6.1): formalize this shape in SkillMetadata once the first real
    storage-backed tool lands.
    """

    def _callback(callback_context: Any) -> None:
        span = trace.get_current_span()
        span.set_attribute("skill_id", skill_id)
        state = callback_context.state if hasattr(callback_context, "state") else None
        routing_choice = state.get("routing_choice") if state is not None else None
        if routing_choice:
            span.set_attribute("routing_choice", routing_choice)

        # Signed URL plumbing — only if caller wired in a ctx + non-empty configs
        if access_context is None or not tool_configs or state is None:
            return
        _populate_signed_urls(tool_configs, access_context, state)

    return _callback


def _populate_signed_urls(
    tool_configs: dict[str, Any],
    ctx: AccessContext,
    state: Any,
) -> None:
    """Resolve tool_configs → folder configs → signed URLs. Never crashes the run.

    Looked-up folders that don't exist or the user can't access are skipped
    silently. If the IAM signer is unavailable, ``build_signed_urls_for_folders``
    sets ``state['signed_urls_unavailable']=True``.
    """
    # Lazy imports: keep callbacks.py light and avoid circular imports with
    # buckets/folder_config, which pulls db.firestore at import time.
    from auth.signed_urls import build_signed_urls_for_folders
    from buckets.folder_config import get_folder

    folder_refs: list[tuple[str, str]] = []
    for _tool, config in tool_configs.items():
        if not isinstance(config, dict):
            continue
        for entry in config.get("bucket_folders", []) or []:
            if isinstance(entry, dict) and "bucket_id" in entry and "folder_id" in entry:
                folder_refs.append((entry["bucket_id"], entry["folder_id"]))

    if not folder_refs:
        return

    folders = []
    for bucket_id, folder_id in folder_refs:
        try:
            folder = get_folder(bucket_id, folder_id)
        except Exception as exc:
            logger.warning("failed to load folder %s/%s: %s", bucket_id, folder_id, exc)
            continue
        if folder is not None:
            folders.append(folder)

    # Populate state even if folders is empty — callers can rely on the key.
    # Use __setitem__ on ADK's state proxy the same way existing callers do.
    temp: dict[str, Any] = {}
    build_signed_urls_for_folders(folders, ctx, state=temp)
    for key in ("signed_urls", "signed_urls_unavailable"):
        if key in temp:
            state[key] = temp[key]


# --- before_agent_callback: document loader ---

# Frontend sets this to True when the user enters a chat by clicking a
# conversation thread from the per-document Conversations panel — signal
# that the document context should be eagerly loaded into the LLM request
# so the agent doesn't have to discover it via load_artifacts (which it
# can fumble — calls with empty args, etc.). Fresh chats keep the standard
# tool-discovered flow.
_STATE_RESUMED_SESSION = "app:resumed_session"
# Tracks which doc ids have been *successfully loaded as artifacts*. Two
# invariants ride on this list:
#   1. The loader is idempotent across turns — re-running with the same
#      ids is a no-op, so adding a tab mid-session only loads the new doc.
#   2. The injector treats every id here as having a saved
#      doc:{id}.json artifact. Stranding an id with no artifact behind
#      it leaves the agent silently without context (the injector skips,
#      the LLM falls back to retrieve_artifact, and "I couldn't find an
#      artifact" lands in front of the user — the 2026-04-28 bug).
# Failures (exception OR blocks=None) are NOT recorded here so a transient
# Firestore hiccup or an in-flight parse self-heals on the next turn.
_STATE_DOCS_LOADED = "app:docs_loaded"
# Map of doc_id -> error string for any doc that failed to load. Per-doc so a
# single bad doc doesn't suppress the error message for a different one.
_STATE_DOC_LOAD_ERROR = "app:doc_load_error"


def make_document_loader() -> Any:
    """Return a before_agent_callback that loads document blocks into session artifacts.

    Reads ``document_ids`` (list[str]) from session state — set by skill_processor
    when one or more documents are attached to the request. Saves each as a
    separate session-scoped artifact ``doc:{id}.json`` (application/json) which
    ``load_artifacts_tool`` auto-injects into the model's context.

    Incremental: tracks loaded ids in ``app:docs_loaded`` (list[str]) so when
    the user adds a tab mid-session we only load the *new* doc, and a failed
    doc isn't retried every turn. Failures are recorded per-doc in
    ``app:doc_load_error`` (dict[str, str]) — non-fatal.
    """

    async def _loader(callback_context: Any) -> None:
        state = getattr(callback_context, "state", None)
        if state is None:
            logger.info("doc loader: skipped — callback_context.state is None")
            return

        document_ids: list[str] = list(state.get("document_ids") or [])
        loaded_raw: list[str] = list(state.get(_STATE_DOCS_LOADED) or [])

        # WARNING level (not INFO) so this single forensic line surfaces in
        # .dev-logs/backend.log without re-configuring Python's root logger.
        # See docs/design/v6.1.0/multi-doc-context-fix.md (1.22) — D1.
        logger.warning(
            "doc loader: turn start — document_ids=%s prior loaded=%s",
            document_ids,
            loaded_raw,
        )

        # Self-heal sessions that were stranded by the pre-2026-04-28 loader,
        # where a failed load still appended the id to _STATE_DOCS_LOADED. The
        # injector's load_artifact then returned nothing and the agent told
        # the user "I couldn't find an artifact". Probe each prior-loaded id;
        # drop ones whose artifact is missing so they re-load below.
        loaded: list[str] = []
        orphans: list[str] = []
        for doc_id in loaded_raw:
            try:
                art = await callback_context.load_artifact(filename=f"doc:{doc_id}.json")
            except Exception as exc:
                logger.warning("doc loader: orphan probe error for %s: %s", doc_id, exc)
                orphans.append(doc_id)
                continue
            if art is None or getattr(art, "inline_data", None) is None:
                orphans.append(doc_id)
                continue
            loaded.append(doc_id)
        if orphans:
            logger.warning(
                "doc loader: dropping %d orphaned id(s) from app:docs_loaded "
                "(no artifact behind them) — will re-load: %s",
                len(orphans),
                orphans,
            )
        loaded_set = set(loaded)

        to_load = [d for d in document_ids if d and d not in loaded_set]
        if not to_load:
            # Initialise the flag so the absence of docs is also recorded.
            state[_STATE_DOCS_LOADED] = loaded
            logger.info("doc loader: nothing to load — verified loaded=%s", loaded)
            return

        logger.info("doc loader: will load %d new doc(s): %s", len(to_load), to_load)

        from google.genai.types import Blob, Part

        from tools.documents.context import build_document_context

        errors: dict[str, str] = dict(state.get(_STATE_DOC_LOAD_ERROR) or {})
        successfully_loaded: list[str] = []

        for doc_id in to_load:
            try:
                _content, blocks = build_document_context(doc_id, mode="blocks")
                if not blocks:
                    errors[doc_id] = (
                        "Document has no parsed content. Re-upload the document to make it available to the AI."
                    )
                    logger.warning("document loader: no blocks for doc:%s — skipping artifact", doc_id)
                    continue
                artifact = Part(
                    inline_data=Blob(
                        data=json.dumps(blocks).encode("utf-8"),
                        mime_type="application/json",
                    )
                )
                await callback_context.save_artifact(
                    filename=f"doc:{doc_id}.json",
                    artifact=artifact,
                )
                successfully_loaded.append(doc_id)
                # Retry succeeded: clear any stale error from a prior turn.
                errors.pop(doc_id, None)
                logger.info(
                    "document artifact saved: doc:%s.json (%d blocks)",
                    doc_id,
                    len(blocks),
                )
            except Exception as exc:
                logger.warning("document loader failed for %s: %s", doc_id, exc)
                errors[doc_id] = str(exc)

        loaded.extend(successfully_loaded)
        state[_STATE_DOCS_LOADED] = loaded
        # Reflect the current error map. Clear it back to {} when a retry
        # resolved every prior failure — leaving "Firestore unavailable"
        # in state for a doc that's now happily attached would mislead
        # the agent. Never introduce the key on a clean first run.
        if errors:
            state[_STATE_DOC_LOAD_ERROR] = errors
        elif _STATE_DOC_LOAD_ERROR in state:
            state[_STATE_DOC_LOAD_ERROR] = {}

        # Stranded-session-prevention (1.23) Option 2: when turn 1
        # requests docs and EVERY one fails, the session row will land
        # with ``documentIds=[]`` and stay invisible to per-doc panels
        # until a future turn succeeds. Per-doc WARNINGs above get lost
        # in noise; this single ERROR is the greppable signal.
        if to_load and not successfully_loaded and not loaded_raw:
            session_for_log = getattr(callback_context, "session", None)
            session_id_for_log = getattr(session_for_log, "id", "?") if session_for_log else "?"
            logger.error(
                "doc loader: TURN-1 INVARIANT VIOLATED — session=%s requested %d doc(s) "
                "%s but every load failed (%s). Session row will have documentIds=[] "
                "and will not appear in any per-doc Conversations panel until a "
                "subsequent turn succeeds.",
                session_id_for_log,
                len(to_load),
                to_load,
                list(errors),
            )

        # Mirror successfully loaded docs onto the ChatSessionIndex so the
        # session shows up under each doc's history panel. Best-effort: if
        # Firestore is down, the artifact load already succeeded — the
        # history panel is a discoverability nicety, not a correctness gate.
        if successfully_loaded:
            session = getattr(callback_context, "session", None)
            session_id = getattr(session, "id", None) if session else None
            if session_id:
                try:
                    from db.chat_sessions import add_session_documents

                    add_session_documents(session_id, successfully_loaded)
                except Exception as exc:
                    logger.warning(
                        "failed to update chat_sessions/%s documentIds: %s",
                        session_id,
                        exc,
                    )

    return _loader


def make_document_injector() -> Any:
    """Return a ``before_model_callback`` that eagerly inlines loaded
    documents into the LLM request whenever any documents are attached
    to the session.

    Why: ADK's standard ``load_artifacts_tool`` makes the agent decide
    whether to call it — and Gemini sometimes calls it with empty
    ``artifact_names``, in which case nothing actually reaches the model
    and the agent confidently says "you haven't provided a document".
    The user has *signalled* intent by attaching the document (clicking
    a doc tab, or resuming a thread that had docs attached), so we skip
    that gamble and put the blocks directly in the LLM request.

    Scope (chat-history-deep-fixes-3 / Bug F): fires whenever
    ``state[_STATE_DOCS_LOADED]`` is non-empty, regardless of whether
    the session is fresh or resumed. Earlier scope ("only resumed")
    was a conservative initial choice that left fresh chats relying on
    Gemini's flaky tool-discovery — the user reported the failure
    end-to-end ("the tool tries to load artifacts but doesn't see the
    doc") so we drop the gate.

    Per-turn behaviour: only fires for the first model call of each turn
    (when the trailing content is the user's text, not a tool
    function_response) so we don't re-inject during in-turn tool
    roundtrips. Each turn's request is rebuilt from session events, so
    we have to inject again on every user turn — the alternative
    (persisting injected content into events) would bloat history.
    """

    async def _injector(callback_context: Any, llm_request: Any) -> None:
        # TTFT: mark the end of the before-model chain on every entry. This
        # is the moment immediately before the model is invoked — perfect
        # anchor for the "Thinking…" stage label. We mark even when there
        # are no docs to inject, since the model is about to run either
        # way.
        from observability.timing import STAGE_BEFORE_MODEL_DONE, get_current_tracker

        get_current_tracker().mark(STAGE_BEFORE_MODEL_DONE, user_label="Thinking…")

        state = getattr(callback_context, "state", None)
        if state is None:
            logger.info("doc injector: skipped — state is None")
            return

        loaded: list[str] = list(state.get(_STATE_DOCS_LOADED) or [])
        if not loaded:
            logger.info(
                "doc injector: skipped — app:docs_loaded is empty (document_ids=%s)",
                state.get("document_ids"),
            )
            return

        contents = getattr(llm_request, "contents", None)
        if not contents:
            logger.info("doc injector: skipped — llm_request.contents empty")
            return
        last = contents[-1]
        if getattr(last, "role", None) != "user":
            logger.info(
                "doc injector: skipped — trailing content role=%s (not 'user')",
                getattr(last, "role", None),
            )
            return
        # If the last user content is actually a function_response from a
        # tool round-trip, this is a follow-up model call mid-turn —
        # don't re-inject.
        last_parts = getattr(last, "parts", None) or []
        if any(getattr(p, "function_response", None) for p in last_parts):
            logger.info("doc injector: skipped — mid-turn tool round-trip")
            return

        from google.genai.types import Content, Part

        injected = 0
        for doc_id in loaded:
            try:
                artifact = await callback_context.load_artifact(filename=f"doc:{doc_id}.json")
            except Exception as exc:
                logger.warning("doc injector: load_artifact failed for %s: %s", doc_id, exc)
                continue
            if not artifact or not getattr(artifact, "inline_data", None):
                logger.warning(
                    "doc injector: artifact missing for %s — orphan in app:docs_loaded "
                    "(loader's orphan recovery will retry next turn)",
                    doc_id,
                )
                continue
            data = artifact.inline_data.data
            if not data:
                logger.warning("doc injector: artifact empty for %s", doc_id)
                continue
            blocks_json = data.decode("utf-8", errors="replace") if isinstance(data, bytes | bytearray) else str(data)
            doc_content = Content(
                role="user",
                parts=[
                    Part.from_text(
                        text=(f"[Attached document: doc:{doc_id}.json — provided by the user]\n{blocks_json}")
                    )
                ],
            )
            # Insert before the latest user message so the model reads
            # docs first, then the question.
            contents.insert(-1, doc_content)
            injected += 1

        logger.info(
            "doc injector: prepended %d/%d document(s) to LLM request (loaded=%s)",
            injected,
            len(loaded),
            loaded,
        )

    return _injector


# --- session index callbacks (CHAT-HISTORY sprint) ---

_STATE_INITIALIZED = "app:chat_session_initialized"
_STATE_TURN_COUNT = "app:chat_session_turn_count"


def make_session_tracker(owner_uid: str, skill_id: str) -> Any:
    """Return a ``before_agent_callback`` that creates the ChatSessionIndex once.

    ADK has no dedicated "session created" hook; ``before_agent_callback``
    fires at the start of every turn. We use the
    ``app:chat_session_initialized`` state flag to run creation only once
    per session.

    ``owner_uid`` and ``skill_id`` are captured in closures from the
    authenticated request + the skill being invoked so we don't re-read
    them on every turn. The skill_id closure is what makes
    ``list_sessions_for_skill`` work — earlier the tracker pulled
    skill_id from session state, but nothing set it there, so every row
    landed in Firestore as ``skillId: "unknown"`` and the per-skill
    sidebar always came back empty.
    """

    def _tracker(callback_context: Any) -> None:
        state = getattr(callback_context, "state", None)
        if state is None:
            return
        if state.get(_STATE_INITIALIZED):
            return

        # First turn of this session — create the index row.
        session = getattr(callback_context, "session", None)
        session_id = getattr(session, "id", None) if session else None
        if not session_id:
            return

        # B1 idempotency (chat-history-fixes v6.1.0): process_skill_request
        # writes the index row synchronously at the top of the SSE stream so
        # GET /api/sessions/{id} works even if the user reloads before this
        # callback fires. If that synchronous write already landed, this
        # callback must NOT re-create the row — that would clobber any
        # title / turnCount / documentIds updates already on it.
        try:
            existing = get_session_index(session_id)
        except Exception as exc:
            logger.warning("idempotency check failed for %s, attempting create: %s", session_id, exc)
            existing = None
        if existing is not None:
            state[_STATE_INITIALIZED] = True
            state[_STATE_TURN_COUNT] = 0
            return

        # Multi-doc sessions: store the full list on the index so
        # ``list_sessions_for_document(doc_id)`` finds this session under
        # each of its docs via ``array_contains``. Access-control still
        # derives from the first doc — that's the session's "anchor" for
        # the initial visibility decision.
        document_ids: list[str] = list(state.get("document_ids") or [])
        anchor_doc_id: str | None = document_ids[0] if document_ids else None

        access_control = _derive_access_control(anchor_doc_id)

        try:
            from db.chat_sessions import create_session_index

            create_session_index(
                session_id=session_id,
                skill_id=skill_id,
                owner_uid=owner_uid,
                access_control=access_control,
                document_ids=document_ids,
            )
            state[_STATE_INITIALIZED] = True
            state[_STATE_TURN_COUNT] = 0
            logger.info("chat_sessions/%s index created (owner=%s)", session_id, owner_uid)
        except Exception as exc:
            logger.warning("failed to create session index for %s: %s", session_id, exc)

    return _tracker


def _derive_access_control(document_id: str | None) -> AccessControl:
    """Derive the initial access control for a new session.

    If the session is attached to a document, copy the document's
    accessControl. Otherwise default to private.
    """
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
        logger.warning("could not fetch document %s for access_control: %s", document_id, exc)
    return AccessControl(type="private")


def _try_generate_title(session: Any) -> str | None:
    """Attempt to generate a title from session events. Returns None on any failure."""
    events = list(getattr(session, "events", None) or [])
    try:
        from db.title_generator import generate_title_fast

        return generate_title_fast(events[:8])
    except Exception as exc:
        logger.warning("title generation raised: %s", exc)
        return None


def _flush_session_index(session_id: str, turn_count: int, title: str | None) -> None:
    """Write counter update (and optionally title) to Firestore."""
    try:
        from db.chat_sessions import update_session_fields

        update: dict[str, Any] = {
            "turnCount": turn_count,
            "lastMessageAt": datetime.now(UTC).isoformat(),
        }
        if title is not None:
            update["title"] = title
        update_session_fields(session_id, update)
    except Exception as exc:
        logger.warning("failed to update session index for %s: %s", session_id, exc)


def make_after_agent_response() -> Any:
    """Return an ``after_agent_callback`` that maintains the ChatSessionIndex.

    After each turn:
    - Increments the in-memory turn counter stored in session state.
    - Flushes ``turnCount`` + ``lastMessageAt`` to Firestore every
      ``_TURN_FLUSH_INTERVAL`` turns.
    - Triggers title generation after exactly turn 2 (first full exchange).
    """

    def _after_response(callback_context: Any) -> None:
        state = getattr(callback_context, "state", None)
        if state is None or not state.get(_STATE_INITIALIZED):
            return

        session = getattr(callback_context, "session", None)
        session_id = getattr(session, "id", None) if session else None
        if not session_id:
            return

        turn_count: int = int(state.get(_STATE_TURN_COUNT) or 0) + 1
        state[_STATE_TURN_COUNT] = turn_count

        # B3 (chat-history-fixes v6.1.0): retry title generation on a later
        # flush turn if turn 2 produced None (thin context). ``state["titleSet"]``
        # is set to True only on a successful generation, so retries stop
        # once the session has a title.
        needs_title_gen = turn_count == 2 or (turn_count >= 4 and not state.get("titleSet"))
        flush_counters = (turn_count % _TURN_FLUSH_INTERVAL == 0) or needs_title_gen
        if not flush_counters:
            return

        title = _try_generate_title(session) if needs_title_gen else None
        if title is not None:
            state["titleSet"] = True
        _flush_session_index(session_id, turn_count, title)

        # B2 (chat-history-fixes v6.1.0): keep ``documentIds`` in sync with
        # the docs the user has open in this session. ``make_document_loader``
        # adds ids to state mid-conversation; without this ArrayUnion sync,
        # ``list_sessions_for_document`` would never see those docs because
        # they were missing from Firestore.
        try:
            add_session_documents(session_id, list(state.get("document_ids") or []))
        except Exception as exc:
            logger.warning("failed to sync documentIds for %s: %s", session_id, exc)

    return _after_response


# --- after_agent_callback (legacy no-op — kept for tests that import it) ---


def _after_agent(callback_context: Any) -> None:
    """Retained for import compatibility; agent factory now uses make_after_agent_response."""
    return None


# --- after_tool_callback ---


def _handle_large_output(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: Any,
) -> Any:
    """Offload oversize tool responses to an ADK artifact.

    Returns the original response untouched when ``len(str(tool_response))``
    is at or below the threshold. For larger responses, saves the full
    payload as a Part-wrapped artifact and returns a short pointer string
    the model can reference.
    """
    text = str(tool_response)
    if len(text) <= _LARGE_OUTPUT_THRESHOLD:
        return tool_response

    tool_name = getattr(tool, "name", "tool")
    artifact_name = f"{tool_name}_response_{tool_context.invocation_id}"
    # Lazy import — avoids pulling google.genai.types at module import time
    # (and keeps the test mock path simple).
    from google.genai import types as genai_types

    part = genai_types.Part.from_text(text=text)
    try:
        tool_context.save_artifact(filename=artifact_name, artifact=part)
    except Exception as exc:  # pragma: no cover - ADK artifact service errors
        logger.warning("save_artifact failed for %s: %s", artifact_name, exc)
        return tool_response

    logger.info("offloaded large tool response to artifact %s (%d chars)", artifact_name, len(text))
    return (
        f"[large response saved as artifact '{artifact_name}' — "
        f"{len(text):,} chars. Load via tool_context.load_artifact('{artifact_name}') "
        f"if you need the full content.]"
    )
