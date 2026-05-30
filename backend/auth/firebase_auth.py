"""
Firebase JWT verification middleware for FastAPI.

Provides:
    - `User`: Pydantic model for an authenticated caller (uid, email, domain,
      group_tags as frozenset from the JWT `groupTags` custom claim).
    - `get_current_user`: FastAPI dependency that parses the `Authorization`
      header, calls `firebase_admin.auth.verify_id_token`, and returns `User`.

Assumes `firebase_admin.initialize_app()` has been called at app startup
(see `fast_api_app.py`). Uses Application Default Credentials (ADC) — on
Cloud Run the attached service account is picked up automatically; locally,
`gcloud auth application-default login` supplies creds.

No PII (email) is logged on success or failure — only `uid` on success, and
the exception type name on failure.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from firebase_admin import auth as fb_auth
from pydantic import BaseModel, ConfigDict, Field

from auth.access_context import build_access_context

logger = logging.getLogger(__name__)


class User(BaseModel):
    """Authenticated caller extracted from a verified auth token.

    Used across all four auth modes (Firebase, Identity Platform,
    LOCAL_MODE stub, anonymous-group-id — sprint 2.11).

    `group_tags` is populated from the JWT `groupTags` custom claim set
    server-side via `firebase_admin.auth.set_custom_user_claims`. Because it
    comes from a signed JWT the client cannot forge it. An absent or empty
    claim lands as an empty frozenset.

    `auth_mode` distinguishes the four modes for downstream code that
    needs to branch on it (e.g. permissions falls back to `group/<gid>`
    lookup for `anonymous_group_id`). Defaults to `"firebase"` for
    back-compat — existing call sites that construct `User` directly
    don't need to change.

    `group_id` is set ONLY when `auth_mode == "anonymous_group_id"`;
    empty string otherwise. Carrying it on User (rather than as a
    side-channel) keeps the permission system and observability hooks
    type-safe.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    email: str = ""
    domain: str = ""
    group_tags: frozenset[str] = Field(default_factory=frozenset)
    auth_mode: str = "firebase"
    group_id: str = ""


def _extract_domain(email: str) -> str:
    """Return the part of `email` after `@`, or `""` if there is no `@`."""
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[1]


def _user_from_decoded_token(decoded: dict[str, Any]) -> User:
    """Build a `User` from a verified Firebase decoded-token dict."""
    email = decoded.get("email") or ""
    raw_tags = decoded.get("groupTags") or []
    group_tags = frozenset(str(t) for t in raw_tags)
    return User(
        uid=decoded["uid"],
        email=email,
        domain=_extract_domain(email),
        group_tags=group_tags,
    )


async def get_current_user(request: Request) -> User:
    """FastAPI dependency: verify `Authorization: Bearer <jwt>` → `User`.

    Raises:
        HTTPException(401): missing header, malformed header (not `Bearer `),
            empty bearer token, or `verify_id_token` rejects the token
            (expired, invalid signature, malformed, revoked).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Malformed Authorization header")
    token = auth_header[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        decoded = fb_auth.verify_id_token(token)
    except fb_auth.ExpiredIdTokenError as exc:
        logger.info("auth: rejected expired token")
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except fb_auth.InvalidIdTokenError as exc:
        logger.info("auth: rejected invalid token")
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    except Exception as exc:
        # Last-resort guard: firebase-admin can raise ValueError on shape errors.
        logger.info("auth: rejected token (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user = _user_from_decoded_token(decoded)
    # Stash a request-scoped AccessContext so route handlers can call
    # `request.state.access.can_access_skill(...)` without re-reading the JWT.
    request.state.access = build_access_context(user)
    logger.info("auth: authenticated uid=%s", user.uid)
    return user


__all__ = ["User", "get_current_user"]
