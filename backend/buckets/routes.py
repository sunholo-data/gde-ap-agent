"""FastAPI routes for bucket + folder CRUD — /api/buckets endpoints.

Follows the same 404-on-deny pattern as skills/routes.py:
    - anon          → 401 (dependency on get_current_user)
    - not visible   → 404 (don't leak existence)
    - visible but not owner → 403 on PUT/DELETE (real forbidden)
    - owner / admin → 200 / 201 / 204

Folders enforce `effective_access` on every write — compute_effective_access
runs before persist so rules can read effectiveAccess directly without
recursion. Parent-access fan-out (bucket accessControl change re-writing
descendant folder effectiveAccess) is **deferred to v6.1** — see
resource-access-control.md §Open questions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from auth import User, get_current_user
from buckets import bucket_config, folder_config
from db.models import AccessControl, BucketConfig, BucketFolderConfig

router = APIRouter(prefix="/api/buckets", tags=["buckets"])


# === Request / Response models ===


class CreateBucketRequest(BaseModel):
    display_name: str = Field(alias="displayName")
    gcs_bucket: str = Field(alias="gcsBucket")
    region: str = "europe-west1"
    access_control: dict = Field(default_factory=lambda: {"type": "private"}, alias="accessControl")
    tags: list[str] = []

    model_config = {"populate_by_name": True}


class UpdateBucketRequest(BaseModel):
    display_name: str | None = Field(default=None, alias="displayName")
    region: str | None = None
    access_control: dict | None = Field(default=None, alias="accessControl")
    tags: list[str] | None = None

    model_config = {"populate_by_name": True}


class CreateFolderRequest(BaseModel):
    path: str
    display_name: str = Field(alias="displayName")
    access_control: dict | None = Field(default=None, alias="accessControl")
    tags: list[str] = []

    model_config = {"populate_by_name": True}


class UpdateFolderRequest(BaseModel):
    display_name: str | None = Field(default=None, alias="displayName")
    access_control: dict | None = Field(default=None, alias="accessControl")
    tags: list[str] | None = None

    model_config = {"populate_by_name": True}


class BucketResponse(BaseModel):
    bucket_id: str = Field(alias="bucketId")
    display_name: str = Field(alias="displayName")
    gcs_bucket: str = Field(alias="gcsBucket")
    region: str
    owner_id: str = Field(alias="ownerId")
    owner_email: str = Field(alias="ownerEmail")
    access_control: dict = Field(alias="accessControl")
    tags: list[str]
    created_at: float = Field(alias="createdAt")
    updated_at: float = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_config(cls, config: BucketConfig) -> BucketResponse:
        return cls.model_validate(config.model_dump(by_alias=True))


class FolderResponse(BaseModel):
    folder_id: str = Field(alias="folderId")
    bucket_id: str = Field(alias="bucketId")
    path: str
    display_name: str = Field(alias="displayName")
    owner_id: str = Field(alias="ownerId")
    access_control: dict | None = Field(alias="accessControl")
    effective_access: dict = Field(alias="effectiveAccess")
    tags: list[str]
    created_at: float = Field(alias="createdAt")
    updated_at: float = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_config(cls, config: BucketFolderConfig) -> FolderResponse:
        return cls.model_validate(config.model_dump(by_alias=True))


# === Helpers ===


def _validate_access_shape(ac: dict) -> None:
    """Surface AccessControl shape errors as 400, not 500."""
    try:
        AccessControl.model_validate(ac)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid accessControl: {exc.errors()[0]['msg']}") from exc


# === Bucket routes ===


@router.get("", response_model=list[BucketResponse])
def list_buckets(
    request: Request,
    owner_id: str | None = Query(None, alias="ownerId"),
    tag: str | None = None,
    access_type: str | None = Query(None, alias="accessType"),
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """List buckets the caller can access."""
    access = request.state.access
    configs = bucket_config.list_buckets(owner_id=owner_id, tag=tag, access_type=access_type, limit=limit)
    visible = [c for c in configs if access.can_access(c)]
    return [BucketResponse.from_config(c) for c in visible]


@router.post("", status_code=201, response_model=BucketResponse)
def create_bucket(req: CreateBucketRequest, user: User = Depends(get_current_user)) -> Any:  # noqa: B008
    """Create a bucket. `ownerId` is always set from the JWT — never client-supplied."""
    _validate_access_shape(req.access_control)
    config = bucket_config.create_bucket(
        display_name=req.display_name,
        gcs_bucket=req.gcs_bucket,
        owner_id=user.uid,
        owner_email=user.email,
        region=req.region,
        accessControl=req.access_control,
        tags=req.tags,
    )
    return BucketResponse.from_config(config)


@router.get("/{bucket_id}", response_model=BucketResponse)
def get_bucket(
    bucket_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Get a bucket by ID. 404 (not 403) if invisible."""
    config = bucket_config.get_bucket(bucket_id)
    if config is None or not request.state.access.can_access(config):
        raise HTTPException(status_code=404, detail="Bucket not found")
    return BucketResponse.from_config(config)


@router.put("/{bucket_id}", response_model=BucketResponse)
def update_bucket(
    bucket_id: str,
    req: UpdateBucketRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Update a bucket. Owner-only; invisible buckets 404."""
    updates = req.model_dump(by_alias=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "accessControl" in updates:
        _validate_access_shape(updates["accessControl"])

    config = bucket_config.get_bucket(bucket_id)
    if config is None or not request.state.access.can_access(config):
        raise HTTPException(status_code=404, detail="Bucket not found")
    if not request.state.access.is_owner(config):
        raise HTTPException(status_code=403, detail="Only the bucket owner can update")

    updated = bucket_config.update_bucket(bucket_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Bucket not found")
    return BucketResponse.from_config(updated)


@router.delete("/{bucket_id}", status_code=204)
def delete_bucket(
    bucket_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> None:
    """Delete a bucket. Owner or admin only; invisible buckets 404."""
    config = bucket_config.get_bucket(bucket_id)
    if config is None or not request.state.access.can_access(config):
        raise HTTPException(status_code=404, detail="Bucket not found")
    if not request.state.access.is_owner(config):
        raise HTTPException(status_code=403, detail="Only the bucket owner can delete")
    bucket_config.delete_bucket(bucket_id)


# === Folder routes ===


def _load_parent_or_404(bucket_id: str, request: Request) -> BucketConfig:
    parent = bucket_config.get_bucket(bucket_id)
    if parent is None or not request.state.access.can_access(parent):
        raise HTTPException(status_code=404, detail="Bucket not found")
    return parent


@router.get("/{bucket_id}/folders", response_model=list[FolderResponse])
def list_folders(
    bucket_id: str,
    request: Request,
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """List folders under a bucket the caller can access."""
    _load_parent_or_404(bucket_id, request)
    access = request.state.access
    configs = folder_config.list_folders(bucket_id, limit=limit)
    visible = [c for c in configs if access.can_access_folder(c)]
    return [FolderResponse.from_config(c) for c in visible]


@router.post("/{bucket_id}/folders", status_code=201, response_model=FolderResponse)
def create_folder(
    bucket_id: str,
    req: CreateFolderRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Create a folder under `bucket_id`. Owner-only on the parent bucket."""
    parent = _load_parent_or_404(bucket_id, request)
    if not request.state.access.is_owner(parent):
        raise HTTPException(status_code=403, detail="Only the bucket owner can create folders")

    if req.access_control is not None:
        _validate_access_shape(req.access_control)

    try:
        config = folder_config.create_folder(
            bucket=parent,
            path=req.path,
            display_name=req.display_name,
            owner_id=user.uid,
            access_control=req.access_control,
            tags=req.tags,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc.errors()[0]["msg"])) from exc
    return FolderResponse.from_config(config)


@router.get("/{bucket_id}/folders/{folder_id}", response_model=FolderResponse)
def get_folder(
    bucket_id: str,
    folder_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Get a folder. 404 if invisible."""
    _load_parent_or_404(bucket_id, request)
    config = folder_config.get_folder(bucket_id, folder_id)
    if config is None or not request.state.access.can_access_folder(config):
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse.from_config(config)


@router.put("/{bucket_id}/folders/{folder_id}", response_model=FolderResponse)
def update_folder(
    bucket_id: str,
    folder_id: str,
    req: UpdateFolderRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Update a folder. Bucket-owner or folder-owner only."""
    parent = _load_parent_or_404(bucket_id, request)
    config = folder_config.get_folder(bucket_id, folder_id)
    if config is None or not request.state.access.can_access_folder(config):
        raise HTTPException(status_code=404, detail="Folder not found")

    updates = req.model_dump(by_alias=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "accessControl" in updates:
        _validate_access_shape(updates["accessControl"])

    is_bucket_owner = request.state.access.is_owner(parent)
    is_folder_owner = user.uid == config.owner_id
    if not (is_bucket_owner or is_folder_owner):
        raise HTTPException(status_code=403, detail="Only the bucket or folder owner can update")

    updated = folder_config.update_folder(parent, folder_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse.from_config(updated)


@router.delete("/{bucket_id}/folders/{folder_id}", status_code=204)
def delete_folder(
    bucket_id: str,
    folder_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> None:
    """Delete a folder. Bucket-owner or folder-owner only."""
    parent = _load_parent_or_404(bucket_id, request)
    config = folder_config.get_folder(bucket_id, folder_id)
    if config is None or not request.state.access.can_access_folder(config):
        raise HTTPException(status_code=404, detail="Folder not found")

    is_bucket_owner = request.state.access.is_owner(parent)
    is_folder_owner = user.uid == config.owner_id
    if not (is_bucket_owner or is_folder_owner):
        raise HTTPException(status_code=403, detail="Only the bucket or folder owner can delete")

    folder_config.delete_folder(bucket_id, folder_id)
