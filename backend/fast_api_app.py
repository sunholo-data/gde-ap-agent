"""
Aitana Platform v6 — FastAPI application.

Uses ADK's get_fast_api_app() for the agent endpoints,
plus custom routes for channels, direct API, and protocols.
"""

import logging
import os
import sys as _sys_for_local_mode

import firebase_admin
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from adk.session import get_artifact_service, get_artifact_service_uri, get_memory_service_uri, get_session_service_uri
from config.gcp import resolve_gcp_credentials, resolve_gcp_project
from config.local_mode import (
    assert_safe_local_mode,
    disabled_services,
    is_local_mode,
    warn_on_session_artifact_pairing,
)
from observability.telemetry import setup_telemetry

# ----------------------------------------------------------------------------
# LOCAL_MODE safety + service banner (must run BEFORE any GCP init)
# ----------------------------------------------------------------------------
# If LOCAL_MODE=1 is paired with K_SERVICE / GAE_ENV / KUBERNETES_SERVICE_HOST
# the auth-bypass stub would be active in a deployed context — refuse to start.
assert_safe_local_mode()
warn_on_session_artifact_pairing()

if is_local_mode():
    # Print the banner directly to stderr so the operator sees it on `make dev`.
    # Logging here is unreliable — uvicorn hasn't wired the app-level logger yet.
    print(
        "[startup] LOCAL_MODE: ON — Firestore in-memory, auth stubbed.\n"
        "[startup]              Disabled: " + ", ".join(disabled_services()) + "\n"
        "[startup]              Data resets on next boot unless LOCAL_MODE_PERSIST=1.",
        file=_sys_for_local_mode.stderr,
        flush=True,
    )

# In LOCAL_MODE, skip Cloud Trace / Cloud Logging telemetry init — no creds, no
# remote exporters. Logs still print to stdout.
if not is_local_mode():
    setup_telemetry()

_log = logging.getLogger(__name__)

# Startup guard: log resolved GCP project so misconfiguration (e.g. shell-level
# GCP_PROJECT pointing at the v5 project) is immediately visible in server output.
_resolved_project = resolve_gcp_project() or "(unset)"
_log.info("GCP project: %s", _resolved_project)

# Touch the singleton here so the upload endpoint and ADK runner share the same instance.
get_artifact_service()

# print() rather than _log.info() because the app-level logger has no handler/level
# wired — uvicorn's own logger is the only one that reliably shows up at startup.
# These three banners are the at-a-glance confirmation that the laptop is hitting
# the cloud backends, not the silent in-memory fallbacks ag_ui_adk used to install.
import sys as _sys  # noqa: E402

_artifact_bucket = os.getenv("ADK_ARTIFACT_BUCKET")
_agent_engine_id = os.getenv("AGENT_ENGINE_ID")
# Local-dev escape hatch (TTFT-OPTIMIZATION 1.21): force in-memory session
# + memory services even when AGENT_ENGINE_ID is set. Cuts laptop TTFT
# from ~9s to ~2s by avoiding Vertex Agent Engine round-trips to
# europe-west1 per turn. Production unaffected — that env var is only
# set in dev shells. See docs/design/v6.1.0/ttft-optimization.md.
_force_local_session = os.getenv("AITANA_LOCAL_SESSION", "").strip().lower() == "memory"
_session_using_vertex = bool(_agent_engine_id) and not _force_local_session


def _service_banner(kind: str) -> str:
    """Compose the [startup] banner line for `Session service:` / `Memory service:`.
    Three cases: Vertex (production / non-overridden dev), forced-in-memory (local
    dev with the escape hatch on), or unset-AGENT_ENGINE_ID (fully local)."""
    if _session_using_vertex:
        if kind == "Session":
            return f"Vertex AI Agent Engine={_agent_engine_id} (chat history persists)"
        return f"Vertex AI Memory Bank={_agent_engine_id} (cross-session recall via load_memory tool)"
    suffix = "chat history" if kind == "Session" else "memory"
    if _force_local_session and _agent_engine_id:
        return f"in-memory (FORCED via AITANA_LOCAL_SESSION=memory — fast local dev; {suffix} will NOT persist)"
    return f"in-memory ({suffix} will NOT persist — set AGENT_ENGINE_ID for Vertex)"


print(f"[startup] Session service: {_service_banner('Session')}", file=_sys.stderr, flush=True)
print(f"[startup] Memory service: {_service_banner('Memory')}", file=_sys.stderr, flush=True)
print(
    "[startup] Artifact service: "
    + (
        f"GCS bucket={_artifact_bucket} (artifacts persist across reloads)"
        if _artifact_bucket
        else "in-memory (artifacts evaporate on reload — set ADK_ARTIFACT_BUCKET for GCS)"
    ),
    file=_sys.stderr,
    flush=True,
)

# Probe ADC once. ADK's otel_to_cloud=True branch calls google.auth.default()
# inside get_fast_api_app to wire Cloud Trace / Cloud Logging exporters, which
# crashes on CI runners with no credentials. Disable the flag when ADC is
# unavailable — Cloud Run and dev laptops still enable GCP telemetry; CI and
# offline tests fall back to no-op exporters.
_adc = resolve_gcp_credentials()
_otel_to_cloud = _adc is not None

# Quota-project guard: when running locally with user ADC against Vertex AI
# Agent Engine, the SDK sets x-goog-user-project from credentials.quota_project_id
# — NOT from the project= argument. A drifted quota_project (commonly left over
# from working on another GCP project) makes every Vertex Sessions call fail
# with an opaque 401 CREDENTIALS_MISSING. Surface it loudly at boot so the
# dev sees the fix command before the first chat turn breaks.
# Cloud Run service accounts don't expose .quota_project_id, so this is a
# no-op there.
if os.getenv("AGENT_ENGINE_ID") and _adc is not None:
    _adc_quota_project = getattr(_adc[0], "quota_project_id", None)
    if _adc_quota_project and _resolved_project != "(unset)" and _adc_quota_project != _resolved_project:
        _log.error(
            "STARTUP ERROR: ADC quota_project=%r does not match GOOGLE_CLOUD_PROJECT=%r. "
            "Vertex AI Agent Engine calls will fail with 401 CREDENTIALS_MISSING. "
            "Fix: gcloud auth application-default set-quota-project %s",
            _adc_quota_project,
            _resolved_project,
            _resolved_project,
        )

# API-key-vs-Vertex guard: when the genai client sees both
# GOOGLE_GENAI_USE_VERTEXAI=true AND GOOGLE_API_KEY in env, it still attaches
# the API key to some Vertex calls. Vertex Sessions / Memory APIs reject
# API-key auth with a 401 "API keys are not supported by this API". The
# shell often has GOOGLE_API_KEY set for other tooling; scripts/dev.sh
# unsets it, but `uv run uvicorn` directly does not — surface it here so
# it cannot fail silently.
if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true" and (
    os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GENAI_API_KEY")
):
    _leaked = next(v for v in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY") if os.getenv(v))
    _log.error(
        "STARTUP ERROR: %s is set alongside GOOGLE_GENAI_USE_VERTEXAI=true. "
        "The genai client will attach the API key to Vertex calls, and Vertex "
        "Sessions/Memory APIs reject API-key auth with 401 CREDENTIALS_MISSING. "
        "Fix: launch via `make dev` (it unsets the API key vars), or "
        "`unset %s` and restart.",
        _leaked,
        _leaked,
    )

# Initialise firebase-admin once, at import time. ADC (the Cloud Run service
# account, or `gcloud auth application-default login` locally) provides
# credentials — no env vars, no secret manager. Called defensively under a
# try/except so hot-reload or re-imports don't crash with ValueError.
# Skip in LOCAL_MODE — no GCP creds, no Firebase to talk to.
if not is_local_mode():
    try:
        firebase_admin.initialize_app()
    except ValueError:
        # Already initialised — safe to ignore.
        pass
else:
    # Seed the in-memory Firestore with workshop fixture so the demo skills
    # are visible the moment the user opens the chat UI. Idempotent.
    from db.local_fixture import seed_local_fixture

    seed_local_fixture()

allow_origins = os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Create the ADK FastAPI app with built-in agent endpoints
# Service URIs are env-var-driven: Vertex AI Agent Engine in production, in-memory locally
app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    session_service_uri=get_session_service_uri(),
    artifact_service_uri=get_artifact_service_uri(),
    memory_service_uri=get_memory_service_uri(),
    allow_origins=allow_origins,
    otel_to_cloud=_otel_to_cloud,
)
app.title = "Sunholo AI Protocol Platform"
app.description = "Open-source AI protocol platform — Skills + AG-UI + A2UI + MCP Apps + A2A on Google ADK"
app.version = "6.0.0"

# Override ADK's built-in /list-apps route (added by web=True) to return the
# canonical APP_NAME constant instead of filesystem subdirectory names. ADK's
# default returns directory names which don't match APP_NAME, so the dev UI's
# "Agent not found: <dir>" error misleads fork authors into guessing wrong paths.
# Route is inserted at position 0 so it wins over the ADK-registered one.
from fastapi.routing import APIRoute  # noqa: E402

from adk.agui import APP_NAME as _APP_NAME  # noqa: E402


async def _list_apps_canonical():
    return [_APP_NAME]


app.router.routes.insert(
    0,
    APIRoute("/list-apps", _list_apps_canonical, methods=["GET"], include_in_schema=False),
)


# --- Health ---


@app.get("/health")
async def health():
    return {"status": "ok", "version": "6.0.0"}


# --- LOCAL_MODE status (public, no auth required) ---
# Frontend banner reads this to know whether to mount itself and to show
# which GCP services are stubbed. Always returns 200 so a fetch failure
# is unambiguously a connectivity issue, not "the backend doesn't know
# about LOCAL_MODE".


@app.get("/api/local-mode-status")
async def local_mode_status():
    return {
        "local_mode": is_local_mode(),
        "disabled_services": disabled_services(),
    }


# --- Custom endpoints (beyond ADK's built-in agent routes) ---

import json  # noqa: E402
import typing  # noqa: E402
from contextlib import AsyncExitStack, asynccontextmanager  # noqa: E402

from fastapi import Depends, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from admin.routes import router as admin_router  # noqa: E402
from auth import User, get_current_user  # noqa: E402
from auth.group_routes import router as group_auth_router  # noqa: E402
from auth.routes import router as auth_router  # noqa: E402
from buckets.routes import router as buckets_router  # noqa: E402
from protocols.a2a import router as a2a_router  # noqa: E402
from protocols.a2ui_surface_action_routes import router as a2ui_surface_action_router  # noqa: E402
from protocols.iframe_context_routes import router as iframe_context_router  # noqa: E402
from protocols.mcp_proxy import router as mcp_proxy_router  # noqa: E402
from protocols.mcp_server import get_mcp_asgi_app  # noqa: E402
from protocols.mcp_server import mcp as mcp_server  # noqa: E402
from protocols.mcp_servers.erp_posting import erp_posting_mcp  # noqa: E402
from protocols.mcp_servers.vendor_master import vendor_master_mcp  # noqa: E402
from protocols.models_route import router as models_router  # noqa: E402
from protocols.session_bootstrap_routes import router as session_bootstrap_router  # noqa: E402
from protocols.sessions_route import router as sessions_router  # noqa: E402
from skills.routes import router as skills_router  # noqa: E402
from skills.skill_processor import SkillNotFoundError, process_skill_request  # noqa: E402
from tools.documents.routes import router as doc_folders_router  # noqa: E402
from tools.documents.upload import router as documents_router  # noqa: E402
from tools.gcs_browser.routes import router as gcs_browser_router  # noqa: E402
from tools.media_utils import router as media_router  # noqa: E402

app.include_router(auth_router)
app.include_router(group_auth_router)
app.include_router(skills_router)
app.include_router(buckets_router)
app.include_router(admin_router)
app.include_router(documents_router)
app.include_router(doc_folders_router)
app.include_router(gcs_browser_router)
app.include_router(media_router)
app.include_router(a2a_router)
app.include_router(models_router)
app.include_router(sessions_router)
app.include_router(session_bootstrap_router)
app.include_router(mcp_proxy_router)
app.include_router(iframe_context_router)
app.include_router(a2ui_surface_action_router)

# ----------------------------------------------------------------------------
# Channel framework (v6.1.0 sprint 1.6 M1)
# ----------------------------------------------------------------------------
# Channels self-register via `ChannelRegistry.register(...)`. `mount_webhooks`
# then exposes `POST /api/{name}/webhook` for each registered channel. M1
# ships the framework with no adapters; M2/M3 register Discord + Email here.
from channels.discord import DiscordChannel  # noqa: E402
from channels.email_ import EmailChannel  # noqa: E402
from channels.registry import ChannelRegistry  # noqa: E402
from channels.telegram_ import TelegramChannel  # noqa: E402
from channels.whatsapp import WhatsAppChannel  # noqa: E402

# Phase 1+ adapters register here.
# Each adapter gates on its required env var so local dev and LOCAL_MODE
# can boot without provider creds. Production sets the env vars via
# Secret Manager (see cloudbuild.yaml).
#
# M2 (Discord): gated on DISCORD_PUBLIC_KEY (needed for webhook verify).
# Adapters that need a persistent gateway connection expose `start_gateway()`,
# which the deployment wires into Cloud Run startup — we don't open the
# gateway from inside `import` because it would block.
_discord_public_key = os.getenv("DISCORD_PUBLIC_KEY", "")
if _discord_public_key:
    ChannelRegistry.register(DiscordChannel())
else:
    _log.info("discord channel not registered: DISCORD_PUBLIC_KEY not set")

# M3 (Email): gated on MAILGUN_SIGNING_KEY.
_mailgun_signing_key = os.getenv("MAILGUN_SIGNING_KEY", "")
if _mailgun_signing_key:
    ChannelRegistry.register(
        EmailChannel(
            signing_key=_mailgun_signing_key,
            api_key=os.getenv("MAILGUN_API_KEY", ""),
            domain=os.getenv("MAILGUN_DOMAIN", ""),
            sender_address=os.getenv("EMAIL_SENDER_ADDRESS", ""),
            api_endpoint=os.getenv("MAILGUN_ENDPOINT", "https://api.eu.mailgun.net"),
        )
    )
else:
    _log.info("email channel not registered: MAILGUN_SIGNING_KEY not set")

# M4 (Telegram): gated on TELEGRAM_BOT_TOKEN.
_telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
if _telegram_bot_token:
    ChannelRegistry.register(TelegramChannel())
else:
    _log.info("telegram channel not registered: TELEGRAM_BOT_TOKEN not set")

# M4 (WhatsApp): gated on TWILIO_ACCOUNT_SID.
_twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
if _twilio_account_sid:
    ChannelRegistry.register(WhatsAppChannel())
else:
    _log.info("whatsapp channel not registered: TWILIO_ACCOUNT_SID not set")

ChannelRegistry.mount_webhooks(app)

# Mount the MCP streamable-HTTP server. FastAPI does NOT propagate lifespan
# events to mounted sub-apps, so the FastMCP session_manager task group
# never starts — every request fails with "Task group is not initialized".
# We compose FastMCP's session_manager.run() into the parent app's lifespan
# so the task group is up for the lifetime of the service.
#
# WORKFLOW-PIPELINE M3: two more in-process FastMCP servers — vendor-master
# and erp-posting — share the same lifespan + mount pattern. Each gets its
# own /mcp/<name> mount point, its own session_manager in the lifespan
# stack. The validator and poster specialists call them via the existing
# tools/mcp/registry McpToolset, so Cloud Trace records them as real MCP
# tool calls (not ad-hoc Python functions).
_parent_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan_with_mcp(app_: FastAPI):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(_parent_lifespan(app_))
        await stack.enter_async_context(mcp_server.session_manager.run())
        await stack.enter_async_context(vendor_master_mcp.session_manager.run())
        await stack.enter_async_context(erp_posting_mcp.session_manager.run())
        yield


app.router.lifespan_context = _lifespan_with_mcp
# Order matters: Starlette matches mounts in registration order, so the
# more specific /mcp/<name> paths must be registered BEFORE the generic
# /mcp catch-all — otherwise /mcp swallows every subpath and the new
# servers 404.
app.mount("/mcp/vendor-master", vendor_master_mcp.streamable_http_app())
app.mount("/mcp/erp-posting", erp_posting_mcp.streamable_http_app())
app.mount("/mcp", get_mcp_asgi_app())


class _StreamSkillRequest(BaseModel):
    """Body schema for POST /api/skill/{skill_id}/stream.

    Accepts two wire formats in one model:

    1. Simple (CLI / tests):
       ``{"message": "hello", "sessionId": "..."}``

    2. AG-UI HttpAgent (frontend):
       ``{"threadId": "...", "runId": "...", "messages": [...], ...}``

    ``effective_message`` and ``effective_session_id`` normalize both shapes
    so the endpoint never needs to branch on which format arrived.
    """

    # Simple format
    message: str = ""
    sessionId: str | None = None
    attachments: list[dict] | None = None
    documentIds: list[str] | None = None

    # AG-UI HttpAgent format (extra fields silently ignored by Pydantic default)
    threadId: str | None = None
    runId: str | None = None
    messages: list[dict] = Field(default_factory=list)
    state: dict | None = None
    forwardedProps: dict | None = None

    model_config = ConfigDict(extra="ignore")

    @property
    def effective_session_id(self) -> str | None:
        return self.sessionId or self.threadId

    @property
    def effective_message(self) -> str:
        if self.message:
            return self.message
        for msg in reversed(self.messages):
            if msg.get("role") == "user" and msg.get("content"):
                return str(msg["content"])
        return ""


def _extract_document_ids(body: "_StreamSkillRequest") -> list[str] | None:
    """Pull the per-turn document_ids list from the wire body.

    Priority (multi-doc-context-fix.md / 1.22 Phase 2):
      1. ``forwardedProps.document_ids`` — the AG-UI HttpAgent path the
         chat page uses; this is the FRESH per-turn signal derived from
         the user's currently-ticked tabs.
      2. ``documentIds`` (top-level) — the simple/CLI/test wire format.
      3. ``state.document_ids`` — legacy fallback. AG-UI's HttpAgent
         mirrors backend STATE_SNAPSHOT events into ``agent.state`` and
         round-trips that state on every subsequent ``runAgent`` call;
         after turn N, the client sends turn N's state back on turn
         N+1. That makes ``state.document_ids`` ONE TURN BEHIND, so
         we read it last as a fallback only.

    Earlier order (state ahead of forwardedProps) caused the Bug-2026-04-28
    multi-doc regression: user opened doc 2 mid-session; backend kept
    seeing only doc 1's id because state had `[doc1]` from the prior
    turn's STATE_SNAPSHOT and forwardedProps was never consulted.
    See backend.log line ``WARNING:adk.callbacks:doc loader: turn start
    — document_ids=['6ecff3e0...']`` and the corresponding frontend
    console line showing ``includedDocIds= ["6ecff3e0...", "41ea1884...",
    "e222aa3d..."]`` — three ids out, one in.

    Returns None when no list is present so the loader treats the turn as
    "no docs attached" rather than "empty selection".
    """
    candidates = (
        (body.forwardedProps or {}).get("document_ids"),
        body.documentIds,
        (body.state or {}).get("document_ids"),
    )
    for value in candidates:
        if isinstance(value, list) and value:
            cleaned = [str(d) for d in value if d]
            if cleaned:
                return cleaned
    return None


def _extract_a2ui_surface_state(body: "_StreamSkillRequest") -> dict | None:
    """Pull the per-turn A2UI surface snapshot from
    ``forwardedProps.a2ui_surface_state`` (the AG-UI HttpAgent path).

    Sprint 2.10. Shape: ``{surfaceId: {catalogId, dataModel}}``. None when
    the frontend hasn't sent any active surface state (no A2UI rendered
    yet, or all surfaces empty). The
    ``wrap_with_a2ui_surface_context`` InstructionProvider treats a
    missing key as "no block to inject" — it's safe to always thread
    the value through.

    Defensive: we only accept dicts. A list / string / number from a
    misbehaving client is dropped rather than crashing the stream.
    """
    raw = (body.forwardedProps or {}).get("a2ui_surface_state")
    if isinstance(raw, dict) and raw:
        return raw
    return None


def _extract_resumed_flag(body: "_StreamSkillRequest") -> bool:
    """True when the frontend signalled this chat was entered by clicking a
    conversation thread from the per-document Conversations panel.

    Read from forwardedProps.resumed_session (the AG-UI HttpAgent path) or
    state.resumed_session (custom state path). Triggers eager doc injection
    in the agent's first LLM request — see make_document_injector.
    """
    candidates = (
        (body.state or {}).get("resumed_session"),
        (body.forwardedProps or {}).get("resumed_session"),
    )
    return any(bool(v) for v in candidates)


from observability.timing import (  # noqa: E402
    STAGE_FIRST_SSE_BYTE,
    STAGE_REQUEST_RECEIVED,
    STAGE_SESSION_INDEX_DONE,
    LatencyTracker,
    reset_current_tracker,
    set_current_tracker,
)


@app.post("/api/skill/{skill_id}/stream")
async def stream_skill(
    skill_id: str,
    body: _StreamSkillRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> StreamingResponse:
    """SSE endpoint: stream AG-UI events for one turn of `skill_id`.

    Non-existent OR non-visible skills both return 404 — do not leak
    skill existence to callers who cannot see them. `get_current_user`
    populates `request.state.access` so the processor can apply the
    same 5-type access rules the CRUD routes use.

    When ``sessionId`` is set and the session is owned by another user the
    caller can see (tagged access), the stream opens read-only:
      1. First frame: ``{"type": "session_meta", "isReadOnly": true}``
      2. Agent is not invoked; message is ignored.
    The caller's UI should disable the composer on ``isReadOnly: true``.
    """
    # Bind a per-request LatencyTracker to the async context so all
    # downstream callbacks (loader, injector, tool hooks) can call
    # ``get_current_tracker().mark(...)`` without explicit plumbing. The
    # finally below resets the binding and emits the structured log.
    tracker = LatencyTracker(
        skill_id=skill_id,
        session_id=body.effective_session_id or "",
        user_id=user.uid,
    )
    tracker.mark(STAGE_REQUEST_RECEIVED)
    _tracker_token = set_current_tracker(tracker)
    request.state.latency_tracker = tracker

    access = request.state.access
    is_read_only = False
    found_existing_session = False
    session_id = body.effective_session_id

    # Only query Firestore when the caller explicitly requested resumption via
    # sessionId (the custom format field). threadId from HttpAgent is always
    # present — treating it as a resumption intent would emit session_meta on
    # every fresh chat, which breaks the AG-UI Zod discriminated union.
    if body.sessionId:
        from db.chat_sessions import get_session_index

        existing = get_session_index(body.sessionId)
        if existing is not None:
            found_existing_session = True
            if not access.can_access(existing):
                raise HTTPException(status_code=403, detail="Access denied to session")
            is_read_only = not access.is_owner(existing)

    extracted_doc_ids = _extract_document_ids(body) if not is_read_only else None
    extracted_resumed = _extract_resumed_flag(body) if not is_read_only else False
    extracted_surface_state = _extract_a2ui_surface_state(body) if not is_read_only else None
    _log.info(
        "stream_skill: skill=%s session=%s read_only=%s document_ids=%s resumed=%s "
        "wire_locations=(top:%s, state:%s, fwd:%s)",
        skill_id,
        session_id,
        is_read_only,
        extracted_doc_ids,
        extracted_resumed,
        body.documentIds,
        (body.state or {}).get("document_ids"),
        (body.forwardedProps or {}).get("document_ids"),
    )

    # The session_index write is the last synchronous step before the SSE
    # stream opens; mark its completion so the timing log distinguishes
    # "Firestore is slow" from "model is slow". Note that
    # ``process_skill_request`` itself does the write — we mark on the way
    # back from its first event, before agent code starts touching the model.
    event_iter = process_skill_request(
        skill_id=skill_id,
        user=user,
        access=access,
        session_id=session_id,
        message=body.effective_message if not is_read_only else "",
        attachments=body.attachments if not is_read_only else None,
        document_ids=extracted_doc_ids,
        resumed_session=extracted_resumed,
        a2ui_surface_state=extracted_surface_state,
    )
    try:
        # Surface SkillNotFoundError *before* returning the StreamingResponse so
        # the client sees a proper 404 rather than a half-open SSE stream.
        first_event: dict | None = await event_iter.__anext__()
    except SkillNotFoundError as exc:
        # Reset context binding even on the error path; no log line for 404.
        reset_current_tracker(_tracker_token)
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except StopAsyncIteration:
        first_event = None

    # ``process_skill_request`` runs the synchronous _ensure_session_index
    # before yielding its first event, so by the time we get here the
    # session index is durable.
    tracker.mark(STAGE_SESSION_INDEX_DONE)

    # Probe param: when set, append a final LATENCY_REPORT Custom event so
    # the ``aiplatform skill probe`` CLI can read the per-stage timings without
    # scraping logs. Free of charge for normal callers.
    probe_mode = request.query_params.get("probe") == "1"

    async def _sse():
        first_byte_marked = False
        try:
            # Only emit session_meta when resuming an existing Firestore session.
            # HttpAgent always sends threadId (even for fresh chats) — we must not
            # treat that as a resumption signal or session_meta leaks into fresh
            # streams and breaks the client's Zod discriminated union.
            if found_existing_session:
                session_meta = json.dumps({"type": "session_meta", "isReadOnly": is_read_only})
                if not first_byte_marked:
                    tracker.mark(STAGE_FIRST_SSE_BYTE)
                    first_byte_marked = True
                yield f"data: {session_meta}\n\n"
            if first_event is not None:
                if not first_byte_marked:
                    tracker.mark(STAGE_FIRST_SSE_BYTE)
                    first_byte_marked = True
                yield f"data: {json.dumps(first_event)}\n\n"
            async for event in event_iter:
                if not first_byte_marked:
                    tracker.mark(STAGE_FIRST_SSE_BYTE)
                    first_byte_marked = True
                yield f"data: {json.dumps(event)}\n\n"
            if probe_mode:
                report = tracker.build_latency_report_event()
                if report is not None:
                    yield f"data: {json.dumps(report.model_dump(by_alias=True, exclude_none=True))}\n\n"
        finally:
            tracker.emit_log()
            reset_current_tracker(_tracker_token)

    return StreamingResponse(_sse(), media_type="text/event-stream")


class _StructuredInvocationRequest(BaseModel):
    """Body schema for POST /api/skill/{skill_id}/structured.

    Audit View "Run Standalone": invokes one specialist directly with a
    JSON Schema-validated input, bypassing the orchestrator.
    """

    # Accept any JSON value — actual shape is constrained by the skill's
    # ``metadata.structuredInput`` JSON Schema, enforced server-side in
    # ``run_structured_invocation``.
    input: typing.Any = None
    sessionId: str | None = None

    model_config = ConfigDict(extra="ignore")


@app.post("/api/skill/{skill_id}/structured")
async def invoke_skill_structured(
    skill_id: str,
    body: _StructuredInvocationRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> JSONResponse:
    """Run one structured-input turn of `skill_id` and return the
    collected AG-UI events as a single JSON response.

    Used by the Audit View panel's "Run Standalone" forms — specialists
    (docparse / ap-validator / ap-poster) declare a JSON Schema in their
    SKILL.md frontmatter under ``metadata.structuredInput``; the form
    validates against that schema before posting, and this endpoint
    re-validates server-side as a defence-in-depth.

    Returns:
        200 with ``{skill_id, duration_ms, text, tool_calls, raw_events}``.
        400 if the input fails schema validation or the skill doesn't
        declare a structuredInput schema.
        404 if the skill is missing or not visible to the caller.
    """
    from skills.structured_invocation import (
        StandaloneAgentRunError,
        StructuredInputInvalidError,
        StructuredInputNotSupportedError,
        run_structured_invocation,
    )

    access = request.state.access
    try:
        result = await run_structured_invocation(
            skill_id=skill_id,
            user=user,
            access=access,
            payload=body.input,
            session_id=body.sessionId,
        )
    except SkillNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Skill not found") from exc
    except StructuredInputNotSupportedError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "structured_input_not_supported", "message": str(exc)},
        ) from exc
    except StructuredInputInvalidError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "structured_input_invalid",
                "message": exc.message,
                "errors": exc.errors,
            },
        ) from exc
    except StandaloneAgentRunError as exc:
        # Upstream agent stream surfaced RUN_ERROR (Vertex session 404,
        # auth, budget, etc). Return 502 — the FE renders the message
        # as a prominent error in the Audit View instead of a silent
        # "0 tool calls" panel.
        raise HTTPException(
            status_code=502,
            detail={
                "error": "agent_run_failed",
                "message": exc.message,
                "code": exc.code,
            },
        ) from exc

    return JSONResponse(result)


# TODO: Direct API endpoints (backward compat with v5 CLI)
# POST /direct/tools/ai-search
# POST /direct/tools/extract-files
# POST /direct/models/gemini
# GET  /direct/models

# TODO: Channel webhooks
# POST /api/telegram/webhook
# POST /api/email/webhook


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1956)
