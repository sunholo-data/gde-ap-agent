"""ADK service factories — env-var-driven backend selection.

Returns Vertex AI Agent Engine backends when ``AGENT_ENGINE_ID`` is set,
in-memory backends otherwise. Local dev points at the **dev Agent Engine**
(same pattern as Firebase/Firestore: laptop talks to real cloud resources via
ADC) so chat history survives uvicorn auto-reloads and is observable in the
same place as Cloud Run dev.

Service URI helpers are used by get_fast_api_app() which accepts URI strings.
Direct service constructors are available for testing and custom wiring.
"""

from __future__ import annotations

import os

from google.adk.apps.app import EventsCompactionConfig
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

from config.gcp import require_gcp_project

# Model-aware compaction intervals. See backend/config/models.yaml for the
# full model registry. EventsCompactionConfig lives on App, not Agent or Runner.
#
# 1M context (Gemini 3.x, GPT-5.4) → compact every 10 turns
# 200K-400K context (Claude, other GPT-5.x) -> compact every 5 turns
#
# NOTE: gpt-5.4 must come before gpt-5 so the more-specific prefix wins.
_COMPACTION_CONFIGS = {
    "gemini-": EventsCompactionConfig(compaction_interval=10, overlap_size=3),
    "gpt-5.4": EventsCompactionConfig(compaction_interval=10, overlap_size=3),
    "claude-": EventsCompactionConfig(compaction_interval=5, overlap_size=2),
    "gpt-5": EventsCompactionConfig(compaction_interval=5, overlap_size=2),
}
_DEFAULT_COMPACTION = EventsCompactionConfig(compaction_interval=5, overlap_size=2)


def get_compaction_config(model_id: str) -> EventsCompactionConfig:
    """Return model-appropriate EventsCompactionConfig.

    Longer context windows (Gemini) compact less often; shorter ones compact more.
    Config is set on App, not on individual Agents.

    Args:
        model_id: The model identifier string (e.g. "gemini-2.5-flash", "claude-sonnet-4-6").

    Returns:
        EventsCompactionConfig tuned for the model's context window size.
    """
    for prefix, config in _COMPACTION_CONFIGS.items():
        if model_id.startswith(prefix):
            return config
    return _DEFAULT_COMPACTION


def _normalize_agent_engine_id(value: str) -> str:
    """Accept either a full resource name or just the numeric ID; return numeric ID.

    ADK's VertexAiSessionService / VertexAiMemoryBankService expect the trailing
    numeric suffix. If a caller passes the full `projects/.../reasoningEngines/NNN`
    resource name, the SDK builds a URL with a doubled `reasoningEngines/` prefix
    and every session call 404s. Strip defensively so either form works.
    """
    return value.rstrip("/").rsplit("/", 1)[-1] if "/" in value else value


def _force_in_memory_session() -> bool:
    """Local-dev escape hatch — force InMemory* services even when
    AGENT_ENGINE_ID is set.

    Why: from a laptop the Vertex Agent Engine session-service round-trip
    to europe-west1 dominates per-turn TTFT (~5.7s of a 9s first-token
    time, per docs/design/v6.1.0/ttft-optimization.md M1 baseline).
    Cloud Run in europe-west1 pays only ~120ms for the same call, so
    production behaviour is unaffected — this flag is for laptops.

    Set ``AITANA_LOCAL_SESSION=memory`` in a developer's shell or
    ``backend/.env`` to opt in. Any other value (including unset) keeps
    Vertex when ``AGENT_ENGINE_ID`` is set, matching the historical
    default.

    The flag intentionally affects BOTH session AND memory services —
    they share the same ``AGENT_ENGINE_ID`` and the same per-turn
    round-trip pattern. Artifact service (GCS) is left alone; it's
    touched on document upload, not on every chat turn.
    """
    return os.environ.get("AITANA_LOCAL_SESSION", "").strip().lower() == "memory"


_session_service_singleton: InMemorySessionService | VertexAiSessionService | None = None


def _reset_session_service_for_tests() -> None:
    """Reset the singleton so tests can exercise different env-var combinations."""
    global _session_service_singleton
    _session_service_singleton = None


def get_session_service() -> InMemorySessionService | VertexAiSessionService:
    """Get session service — Vertex AI Agent Engine or in-memory.

    Returns a module-level singleton so all callers (skill_processor, messages
    endpoint) share the same in-memory store in local dev. In prod the Vertex
    AI service is stateless so multiple instances would be fine, but a
    singleton is still cheaper to construct.
    """
    global _session_service_singleton
    if _session_service_singleton is None:
        agent_engine_id = os.environ.get("AGENT_ENGINE_ID")
        if agent_engine_id and not _force_in_memory_session():
            _session_service_singleton = VertexAiSessionService(
                project=require_gcp_project(),
                location=os.environ["GOOGLE_CLOUD_LOCATION"],
                agent_engine_id=_normalize_agent_engine_id(agent_engine_id),
            )
        else:
            _session_service_singleton = InMemorySessionService()
    return _session_service_singleton


def get_memory_service() -> InMemoryMemoryService | VertexAiMemoryBankService:
    """Get memory service — Vertex AI Agent Engine or in-memory."""
    agent_engine_id = os.environ.get("AGENT_ENGINE_ID")
    if agent_engine_id and not _force_in_memory_session():
        return VertexAiMemoryBankService(
            project=require_gcp_project(),
            location=os.environ["GOOGLE_CLOUD_LOCATION"],
            agent_engine_id=_normalize_agent_engine_id(agent_engine_id),
        )
    return InMemoryMemoryService()


_artifact_service_singleton: InMemoryArtifactService | GcsArtifactService | None = None


def _reset_artifact_service_for_tests() -> None:
    """Reset the singleton so tests can exercise different env-var combinations."""
    global _artifact_service_singleton
    _artifact_service_singleton = None


def get_artifact_service() -> InMemoryArtifactService | GcsArtifactService:
    """Get artifact service — GCS or in-memory, process-level singleton.

    Singleton ensures the upload endpoint and ADK runner share the same
    InMemoryArtifactService in local dev. In prod GCS is shared by bucket name
    and a singleton is still cheaper to construct.
    """
    global _artifact_service_singleton
    if _artifact_service_singleton is None:
        bucket = os.environ.get("ADK_ARTIFACT_BUCKET")
        if bucket:
            _artifact_service_singleton = GcsArtifactService(bucket_name=bucket)
        else:
            _artifact_service_singleton = InMemoryArtifactService()
    return _artifact_service_singleton


# --- URI helpers for get_fast_api_app() ---


def get_session_service_uri() -> str | None:
    """Get session service URI for get_fast_api_app(). None = in-memory."""
    agent_engine_id = os.environ.get("AGENT_ENGINE_ID")
    if agent_engine_id and not _force_in_memory_session():
        return f"agentengine://{_normalize_agent_engine_id(agent_engine_id)}"
    return None


def get_artifact_service_uri() -> str | None:
    """Get artifact service URI for get_fast_api_app(). None = in-memory."""
    bucket = os.environ.get("ADK_ARTIFACT_BUCKET")
    if bucket:
        return f"gs://{bucket}"
    return None


def get_memory_service_uri() -> str | None:
    """Get memory service URI for get_fast_api_app(). None = in-memory."""
    agent_engine_id = os.environ.get("AGENT_ENGINE_ID")
    if agent_engine_id and not _force_in_memory_session():
        return f"agentengine://{_normalize_agent_engine_id(agent_engine_id)}"
    return None
