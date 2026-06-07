"""ADK FunctionTools for org-scoped document discovery and load.

Two tools the ap-orchestrator can call to surface documents that live
in the deploy's bound GCS bucket (configured via the
`A2A_AGENT_DOCUMENTS_BUCKET` env var — see `protocols.a2a_org_bucket`):

- `list_org_documents(prefix)` — returns name/size/mimeType/timeCreated
  per object. Empty list when no bucket bound; never 500s.

- `read_org_document(name)` — fetches an object by name, saves it as a
  `doc:{id}.json` session artifact, appends the minted document_id to
  `state["document_ids"]` so the existing `make_document_loader` picks
  it up alongside any A2A-uploaded files.

ADK FunctionTool detection
--------------------------
ADK auto-wraps any plain async function passed in an agent's `tools=[]`
list. We expose the two functions directly. ToolContext arrives as the
last argument (per ADK's tool-binding convention) and gives us access
to session state and the artifact_service via the tool's runner.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def list_org_documents(prefix: str = "", tool_context: Any = None) -> list[dict[str, Any]]:
    """List documents in this agent's bound GCS bucket.

    Use this when the user asks about existing organisational documents
    (invoices already uploaded, vendor master records, contracts,
    policies) before deciding to extract from any peer-supplied
    attachments. Returns an empty list if no bucket is bound to this
    deploy — answer from text context only in that case.

    Args:
        prefix: Optional path prefix to filter within the bucket
            (e.g. "vendor-master/" or "2026-Q1/"). Empty by default
            returns top-level objects.
        tool_context: Injected by ADK; do not pass explicitly.

    Returns:
        List of dicts. Each has keys: name (object path within bucket),
        size (bytes), mimeType (content-type), timeCreated (ISO
        timestamp). Empty list = no documents available; the model
        should answer from context only.
    """
    from protocols.a2a_org_bucket import get_bound_bucket, list_documents_in_bucket

    bucket = get_bound_bucket()
    if bucket is None:
        logger.info("list_org_documents: no bound bucket — returning []")
        return []

    return await list_documents_in_bucket(bucket, prefix=prefix or "")


async def read_org_document(name: str, tool_context: Any = None) -> dict[str, Any]:
    """Load an org document into the current session for the agent to use.

    Call this AFTER `list_org_documents` once you've identified the
    specific document needed. The fetched bytes land as a session
    artifact and a document_id is appended to session state; the
    existing document-loader callback picks it up on the next agent
    turn so the orchestrator can reason about its content.

    Args:
        name: Object name within the bucket, as returned by
            `list_org_documents` in the `name` field.
        tool_context: Injected by ADK; do not pass explicitly.

    Returns:
        A dict with keys:
            ok (bool): True if loaded, False otherwise
            doc_id (str | None): Minted document_id on success
            message (str): Human-readable status for the model
    """
    from protocols.a2a_org_bucket import get_bound_bucket, read_document_from_bucket

    bucket = get_bound_bucket()
    if bucket is None:
        return {
            "ok": False,
            "doc_id": None,
            "message": "No organisational bucket is bound to this deploy.",
        }

    # tool_context exposes the runner + session triple through ADK's
    # public API. We need (app_name, user_id, session_id) to write the
    # artifact correctly.
    runner = getattr(tool_context, "runner", None)
    if runner is None:
        # In ADK FunctionTool execution, tool_context exposes the runner
        # via private attribute fallback; try both shapes.
        runner = getattr(tool_context, "_runner", None)
    if runner is None:
        logger.warning("read_org_document: tool_context has no runner; cannot save artifact")
        return {
            "ok": False,
            "doc_id": None,
            "message": "Tool context missing runner reference.",
        }

    invocation_context = getattr(tool_context, "_invocation_context", None) or getattr(
        tool_context, "invocation_context", None
    )
    if invocation_context is None:
        logger.warning("read_org_document: tool_context has no invocation context")
        return {
            "ok": False,
            "doc_id": None,
            "message": "Tool context missing invocation context.",
        }

    app_name = invocation_context.app_name
    session = invocation_context.session
    user_id = session.user_id
    session_id = session.id

    doc_id = await read_document_from_bucket(
        bucket,
        name,
        runner=runner,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if doc_id is None:
        return {
            "ok": False,
            "doc_id": None,
            "message": f"Failed to load gs://{bucket.replace('gs://', '')}{name} — check object exists and SA has read access.",
        }

    # Append to state["document_ids"] so make_document_loader sees it.
    state = getattr(tool_context, "state", None)
    if state is not None:
        existing = list(state.get("document_ids") or [])
        if doc_id not in existing:
            state["document_ids"] = [*existing, doc_id]

    return {
        "ok": True,
        "doc_id": doc_id,
        "message": f"Loaded {name} into session as doc:{doc_id}.json. Use it in your next response.",
    }
