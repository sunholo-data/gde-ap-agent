"""FastAPI router for /api/admin/* endpoints.

Admin routes are gated by `_assert_caller_is_service_account` (Google
ID token + SA email allowlist). Never expose these to end users — they
exist to support Cloud Build deploy hooks and ops runbooks.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from admin import platform_seed
from admin.auth import _assert_caller_is_service_account

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/seed-platform-skills")
def seed_platform_skills(request: Request) -> dict[str, Any]:
    """Idempotently seed the default platform-owned skills.

    Hit once per deploy by the Cloud Build seed step. Returns a JSON
    SeedSummary so Cloud Build logs capture what happened.
    """
    _assert_caller_is_service_account(request)
    summary = platform_seed.seed()
    return summary.as_dict()
