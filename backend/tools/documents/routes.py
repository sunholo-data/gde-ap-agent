"""FastAPI routes for user document folders — /api/folders and /api/sessions context.

User-facing document organization layer. Distinct from the storage-ACL
bucket/folder system in backend/buckets/ which manages GCS namespace config.

These folders group user uploads within their per-client GCS bucket, keyed
by the user's email domain (see db/clients.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db.folders as folders_db
from auth import User, get_current_user
from db.clients import resolve_documents_bucket
from db.firestore import delete_document as _delete_firestore_doc
from db.firestore import get_document as _get_firestore_doc
from db.firestore import set_document as _set_firestore_doc

log = logging.getLogger(__name__)

router = APIRouter(tags=["doc-folders"])

_CurrentUser = Annotated[User, Depends(get_current_user)]
_ACCESS_DENIED = "Access denied"


class _CreateFolderRequest(BaseModel):
    name: str


class _FolderResponse(BaseModel):
    id: str
    name: str
    userId: str
    docCount: int = 0
    parsedCount: int = 0


class _FoldersListResponse(BaseModel):
    folders: list[_FolderResponse]


class _DocumentsListResponse(BaseModel):
    documents: list[dict]


@router.post("/api/folders", status_code=201)
def create_folder(body: _CreateFolderRequest, user: _CurrentUser) -> _FolderResponse:
    result = folders_db.create_folder(user_id=user.uid, name=body.name)
    return _FolderResponse(**result)


@router.get("/api/folders")
def list_folders(user: _CurrentUser) -> _FoldersListResponse:
    items = folders_db.list_folders(user_id=user.uid)
    return _FoldersListResponse(folders=[_FolderResponse(**f) for f in items])


@router.get("/api/folders/{folder_id}/documents")
def list_folder_documents(folder_id: str, user: _CurrentUser) -> _DocumentsListResponse:
    folder = folders_db.get_folder(user_id=user.uid, folder_id=folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.get("userId") != user.uid:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)
    docs = folders_db.list_folder_documents(user_id=user.uid, folder_id=folder_id)
    return _DocumentsListResponse(documents=docs)


_PARSED_DOCS_COLLECTION = "parsed_documents"


@router.get("/api/documents/{doc_id}")
def get_document(doc_id: str, user: _CurrentUser) -> dict:
    """Fetch a single parsed document by ID.

    Returns the full document record including blocks for frontend rendering.
    """
    doc = _get_firestore_doc(_PARSED_DOCS_COLLECTION, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.get("userId") != user.uid:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)
    doc.setdefault("id", doc_id)
    return doc


@router.post("/api/documents/{doc_id}/reparse")
async def reparse_document(doc_id: str, user: _CurrentUser) -> dict:
    """Re-run AILANG Parse on an existing document using its stored GCS URL.

    Use this to populate blocks for documents uploaded before the AI pipeline
    was wired, or to retry a failed parse after a transient AILANG error.
    Returns the updated parseStatus and blockCount.
    """
    from tools.documents.upload import _run_parse

    doc = _get_firestore_doc(_PARSED_DOCS_COLLECTION, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.get("userId") != user.uid:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)

    gs_url: str | None = doc.get("sourceUrl")
    if not gs_url:
        raise HTTPException(status_code=422, detail="Document has no GCS source URL — cannot reparse")

    log.info("Reparsing doc %s from %s", doc_id, gs_url)
    status, blocks, elapsed_ms, error = await _run_parse(gs_url)

    now = datetime.now(UTC)
    update: dict = {
        "parseStatus": status,
        "status": status,
        "blocks": blocks if status == "parsed" else [],
        "blockCount": len(blocks) if status == "parsed" else None,
        "tableCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "table") if blocks else None,
        "imageCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "image") if blocks else None,
        "changeCount": sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "change") if blocks else None,
        "parsedMs": elapsed_ms if status == "parsed" else None,
        "parseError": error if status == "failed" else None,
        "parsedAt": now.isoformat() if status == "parsed" else None,
        "updatedAt": now.isoformat(),
    }
    _set_firestore_doc(_PARSED_DOCS_COLLECTION, doc_id, update, merge=True)
    log.info("Reparse complete for doc %s: status=%s blocks=%d", doc_id, status, len(blocks))
    return {"docId": doc_id, "parseStatus": status, "blockCount": len(blocks), "parseError": error}


@router.delete("/api/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user: _CurrentUser) -> None:
    """Delete a document: removes the Firestore record and the GCS file."""
    doc = _get_firestore_doc(_PARSED_DOCS_COLLECTION, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.get("userId") != user.uid:
        raise HTTPException(status_code=403, detail=_ACCESS_DENIED)

    # Delete GCS file — best-effort, don't fail the whole request if it's missing
    storage_path: str | None = doc.get("storagePath")
    if storage_path:
        try:
            from google.cloud import storage as gcs

            bucket_name = resolve_documents_bucket(user)
            gcs.Client().bucket(bucket_name).blob(storage_path).delete()
            log.info("Deleted GCS object gs://%s/%s", bucket_name, storage_path)
        except Exception as exc:
            log.warning("GCS delete failed for %s (continuing): %s", storage_path, exc)

    _delete_firestore_doc(_PARSED_DOCS_COLLECTION, doc_id)
    log.info("Deleted document %s", doc_id)
