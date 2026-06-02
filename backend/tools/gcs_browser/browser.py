"""GCS bucket browser — list objects and import to AP pipeline."""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from fastapi import HTTPException
from google.cloud import storage
from pydantic import BaseModel, Field

import db.folders as folders_db
from auth import User
from db.clients import resolve_documents_bucket
from tools.documents.upload import (
    _ALLOWED_EXTENSIONS,
    _EXTENSION_CONTENT_TYPES,
    ParsedDocumentResponse,
    _ParseResult,
    _run_parse,
    _store_document,
    _upload_to_gcs,
)

log = logging.getLogger(__name__)

# GCS bucket name: 3-63 chars, lowercase letters/digits/hyphens/underscores/dots,
# must start and end with a letter or digit.
GCS_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")


def validate_bucket_name(name: str) -> str:
    """Return name if valid GCS bucket name, else raise ValueError."""
    if not GCS_BUCKET_NAME_RE.match(name):
        raise ValueError(f"Invalid GCS bucket name: {name!r}")
    return name


class GCSObject(BaseModel):
    name: str
    display_name: str = Field(alias="displayName")
    size: int
    content_type: str = Field(alias="contentType")
    updated: str

    model_config = {"populate_by_name": True}


class GCSListResponse(BaseModel):
    bucket: str
    prefix: str
    objects: list[GCSObject]
    prefixes: list[str]
    error: str | None = None
    sa_email: str | None = None


def list_gcs_objects(
    bucket_name: str,
    prefix: str = "",
    delimiter: str = "/",
) -> GCSListResponse:
    """List objects in a GCS bucket.

    The sentinel ``"demo"`` resolves to the ``AP_DEMO_BUCKET`` env var.
    Raises ValueError for syntactically invalid bucket names.
    """
    if bucket_name == "demo":
        actual_bucket = os.getenv("AP_DEMO_BUCKET", "gde-ap-agent-demo-invoices")
    else:
        validate_bucket_name(bucket_name)
        actual_bucket = bucket_name

    try:
        client = storage.Client()
        bkt = client.bucket(actual_bucket)
        blobs_iter = bkt.list_blobs(prefix=prefix, delimiter=delimiter)

        objects: list[GCSObject] = []
        for blob in blobs_iter:
            display = PurePosixPath(blob.name).name or blob.name
            objects.append(
                GCSObject(
                    name=blob.name,
                    display_name=display,
                    size=blob.size or 0,
                    content_type=blob.content_type or "application/octet-stream",
                    updated=blob.updated.isoformat() if blob.updated else "",
                )
            )

        prefixes: list[str] = list(getattr(blobs_iter, "prefixes", None) or [])

        return GCSListResponse(
            bucket=actual_bucket,
            prefix=prefix,
            objects=objects,
            prefixes=prefixes,
        )

    except Exception as exc:
        from google.api_core.exceptions import Forbidden

        if isinstance(exc, Forbidden):
            sa_email: str | None = None
            try:
                import google.auth

                creds, _ = google.auth.default()
                sa_email = getattr(creds, "service_account_email", None)
            except Exception:
                pass
            return GCSListResponse(
                bucket=actual_bucket,
                prefix=prefix,
                objects=[],
                prefixes=[],
                error=str(exc),
                sa_email=sa_email,
            )
        raise


async def import_gcs_object(
    user: User,
    bucket_name: str,
    object_path: str,
    folder_id: str = "",
    folder_name: str = "",
    skill_id: str = "",
) -> ParsedDocumentResponse:
    """Download a GCS object and push it through the AP parse pipeline.

    Folder routing priority:
      1. `folder_id` — explicit pointer to an existing folder
      2. `folder_name` — human-readable name; find-or-create per user
         (eg. "Example Invoices" from the demo bucket source, or
         "gs://my-bucket" from a user-supplied bucket)
      3. Default — first folder, or "Uploads YYYY-MM-DD" if none
    """
    if bucket_name == "demo":
        actual_bucket = os.getenv("AP_DEMO_BUCKET", "gde-ap-agent-demo-invoices")
    else:
        try:
            validate_bucket_name(bucket_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        actual_bucket = bucket_name

    ext = PurePosixPath(object_path).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext!r} is not supported. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    original_filename = PurePosixPath(object_path).name
    if folder_id.strip():
        effective_folder_id = folder_id.strip()
    elif folder_name.strip():
        effective_folder_id = folders_db.find_or_create_folder_by_name(user.uid, folder_name)
    else:
        effective_folder_id = folders_db.ensure_default_folder(user.uid)
    dest_bucket = resolve_documents_bucket(user)

    # Download from the source GCS bucket
    client = storage.Client()
    src_blob = client.bucket(actual_bucket).blob(object_path)
    file_bytes = src_blob.download_as_bytes()
    content_type = _EXTENSION_CONTENT_TYPES.get(ext) or src_blob.content_type or "application/octet-stream"

    doc_id = str(uuid.uuid4())
    storage_path = f"users/{user.uid}/docs/{effective_folder_id}/{original_filename}"
    gs_url = f"gs://{dest_bucket}/{storage_path}"
    now = datetime.now(UTC)

    _upload_to_gcs(dest_bucket, storage_path, file_bytes, content_type, user.uid, original_filename)

    parse_status, blocks, parsed_ms, parse_error = await _run_parse(gs_url)

    _store_document(
        doc_id,
        user_id=user.uid,
        skill_id=skill_id,
        gs_url=gs_url,
        storage_path=storage_path,
        original_filename=original_filename,
        source_format=ext.lstrip("."),
        folder_id=effective_folder_id,
        parse_result=_ParseResult(parse_status, blocks, parse_error, parsed_ms),
        now=now,
    )

    return ParsedDocumentResponse(
        docId=doc_id,
        status=parse_status,
        originalFilename=original_filename,
        blocksCount=len(blocks),
        storagePath=storage_path,
        folderId=effective_folder_id,
    )
