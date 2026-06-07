"""Org-scoped GCS bucket access for A2A peer queries.

Scenario B of the A2A-FILES sprint. Pairs with the `list_org_documents`
and `read_org_document` tools in `backend/tools/org_documents.py`.

What this solves
----------------
Peer agents (Gemini Enterprise especially) want to ask about documents
that already exist in the deploy's GCS workspace — vendor master files,
historical invoices, approval policies. Without this, every peer query
would need a fresh `FilePart` upload, defeating the value of the agent
having a curated knowledge corpus.

Binding storage — v1 design
---------------------------
ONE bucket per deploy, configured via `A2A_AGENT_DOCUMENTS_BUCKET`
(e.g. `gs://gde-ap-agent-demo-invoices/`). When the env var is unset,
`get_bound_bucket()` returns `None` and the tools degrade gracefully
to an empty list — never 500.

What was rejected during sprint planning
----------------------------------------
The original design proposed per-registration bindings via Discovery
Engine `metadata.gcs_documents_bucket`. **The pre-flight curl rejected
that field** with INVALID_ARGUMENT — Discovery Engine's Agent resource
schema doesn't have a top-level `metadata` field. We also considered
Firestore-backed bindings keyed on `agent_resource_name`, but A2A
peers don't reliably carry registration identity through to the
backend, so the lookup key would be ambiguous. Per-deploy was the
fastest path to a shipping primitive; multi-tenant identification is
a clean follow-up sprint when we know what header GE sends (if any).

Security note
-------------
The Cloud Run service account needs `roles/storage.objectViewer` on
the bound bucket. No wildcard access; the SA is granted explicitly
per-bucket. If the env var is set but the SA can't read, list returns
`[]` with a logged warning rather than 500-ing.

Size limits
-----------
List is capped at `A2A_ORG_BUCKET_LIST_LIMIT` (default 100) so a peer
asking for documents from a 10k-object bucket doesn't blow up the
model's context. The orchestrator's instructions tell it to use the
`prefix` arg for narrower listings.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DEFAULT_LIST_LIMIT = 100


def get_bound_bucket() -> str | None:
    """Return the bound bucket URI for this deploy, or None.

    Reads `A2A_AGENT_DOCUMENTS_BUCKET` env var. Validates the prefix
    (`gs://`) and returns the URI unchanged so the GCS client can
    consume it directly. Returns None on unset/malformed values rather
    than raising — the tools fall back to a graceful "no documents
    available" response.
    """
    raw = os.environ.get("A2A_AGENT_DOCUMENTS_BUCKET", "").strip()
    if not raw:
        return None
    if not raw.startswith("gs://"):
        logger.warning(
            "A2A_AGENT_DOCUMENTS_BUCKET=%r does not start with gs://; ignoring",
            raw,
        )
        return None
    return raw.rstrip("/") + "/"  # Normalise trailing slash


def _list_limit() -> int:
    raw = os.environ.get("A2A_ORG_BUCKET_LIST_LIMIT", "")
    if not raw:
        return _DEFAULT_LIST_LIMIT
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_LIST_LIMIT


def _parse_bucket_uri(bucket_uri: str) -> tuple[str, str]:
    """Split a gs://bucket/prefix URI into (bucket_name, prefix).

    Allows the env var to point at a sub-prefix within a bucket so a
    single shared bucket can serve multiple deploys via path isolation.
    """
    parsed = urlparse(bucket_uri)
    if parsed.scheme != "gs":
        msg = f"Expected gs:// URI, got {bucket_uri!r}"
        raise ValueError(msg)
    return parsed.netloc, parsed.path.lstrip("/")


@lru_cache(maxsize=1)
def _gcs_client() -> Any:
    """Lazy singleton — keeps the GCS SDK out of cold-start path for
    deploys that don't use this feature. Cached at module level so
    repeated tool calls don't re-init the client.
    """
    from google.cloud import storage

    return storage.Client()


async def list_documents_in_bucket(bucket_uri: str, *, prefix: str = "") -> list[dict[str, Any]]:
    """LIST objects in the bound bucket; return per-object metadata.

    Returns `[]` on:
      - Unbound deploy (caller already short-circuits but defence in depth)
      - SA can't read (logged WARNING)
      - Bucket doesn't exist (logged WARNING)

    Each returned object has: name, size, mimeType, timeCreated. The
    list is capped at A2A_ORG_BUCKET_LIST_LIMIT (default 100). Prefix
    is concatenated with any prefix encoded in the bucket_uri itself.
    """
    try:
        bucket_name, base_prefix = _parse_bucket_uri(bucket_uri)
    except ValueError as exc:
        logger.warning("list_documents_in_bucket: bad bucket URI: %s", exc)
        return []

    full_prefix = f"{base_prefix}{prefix}".lstrip("/")

    try:
        client = _gcs_client()
        bucket = client.bucket(bucket_name)
        # max_results applied client-side via iteration so we never page
        # past the limit even if the bucket has many more objects.
        limit = _list_limit()
        items: list[dict[str, Any]] = []
        for blob in client.list_blobs(bucket, prefix=full_prefix, max_results=limit):
            items.append(
                {
                    "name": blob.name,
                    "size": blob.size,
                    "mimeType": blob.content_type,
                    "timeCreated": blob.time_created.isoformat() if blob.time_created else None,
                }
            )
        logger.info(
            "list_documents_in_bucket: bucket=%s prefix=%r returned %d object(s)",
            bucket_name,
            full_prefix,
            len(items),
        )
        return items
    except Exception:
        logger.exception(
            "list_documents_in_bucket: failed for bucket=%s prefix=%r — returning []",
            bucket_uri,
            full_prefix,
        )
        return []


async def read_document_from_bucket(
    bucket_uri: str,
    name: str,
    *,
    runner: Any,
    app_name: str,
    user_id: str,
    session_id: str,
) -> str | None:
    """Fetch an object from the bound bucket; save as `doc:{id}.json` artifact.

    Returns the minted `document_id` on success, None on failure. The
    artifact format mirrors what the AG-UI doc-loader writes: a JSON
    blob carrying a single block with the inline bytes (base64) plus
    metadata. The orchestrator's `make_document_loader` callback picks
    it up via the standard `state["document_ids"]` path.
    """
    import base64
    import json
    import uuid

    try:
        bucket_name, base_prefix = _parse_bucket_uri(bucket_uri)
    except ValueError as exc:
        logger.warning("read_document_from_bucket: bad bucket URI: %s", exc)
        return None

    object_name = f"{base_prefix}{name}".lstrip("/")

    try:
        client = _gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        data = blob.download_as_bytes()
        content_type = blob.content_type or "application/octet-stream"
        display_name = name.rsplit("/", 1)[-1] or name
    except Exception:
        logger.exception(
            "read_document_from_bucket: download failed for gs://%s/%s",
            bucket_name,
            object_name,
        )
        return None

    doc_id = str(uuid.uuid4())
    block = {
        "kind": "a2a-org-bucket-file",
        "displayName": display_name,
        "mimeType": content_type,
        "bytesBase64": base64.b64encode(data).decode("ascii"),
        "sourceUri": f"gs://{bucket_name}/{object_name}",
    }

    from google.genai.types import Blob, Part

    artifact = Part(
        inline_data=Blob(
            data=json.dumps([block]).encode("utf-8"),
            mime_type="application/json",
        )
    )

    try:
        await runner.artifact_service.save_artifact(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            filename=f"doc:{doc_id}.json",
            artifact=artifact,
        )
        logger.info(
            "read_document_from_bucket: saved gs://%s/%s as doc:%s.json (%d bytes)",
            bucket_name,
            object_name,
            doc_id,
            len(data),
        )
        return doc_id
    except Exception:
        logger.exception(
            "read_document_from_bucket: artifact save failed for gs://%s/%s",
            bucket_name,
            object_name,
        )
        return None
