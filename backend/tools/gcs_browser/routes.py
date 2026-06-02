"""FastAPI routes for GCS browser: list objects + import to AP pipeline."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import User, get_current_user
from tools.gcs_browser.browser import import_gcs_object, list_gcs_objects

_CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/api/gcs", tags=["gcs"])


class GCSImportRequest(BaseModel):
    bucket: str
    path: str
    folder_id: str = ""
    skill_id: str = ""


@router.get("/list")
def list_objects(
    bucket: str = Query(...),
    prefix: str = Query(default=""),
    delimiter: str = Query(default="/"),
) -> dict:
    """List objects in a GCS bucket."""
    try:
        result = list_gcs_objects(bucket, prefix=prefix, delimiter=delimiter)
        return result.model_dump(by_alias=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import")
async def import_object(
    user: _CurrentUser,
    body: GCSImportRequest,
) -> dict:
    """Import a GCS object into the AP document pipeline."""
    result = await import_gcs_object(
        user=user,
        bucket_name=body.bucket,
        object_path=body.path,
        folder_id=body.folder_id,
        skill_id=body.skill_id,
    )
    return result.model_dump(by_alias=True)
