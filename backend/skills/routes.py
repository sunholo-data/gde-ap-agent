"""FastAPI routes for skill CRUD — /api/skills endpoints.

All routes are authenticated (`Depends(get_current_user)`) except
`GET /api/skills/marketplace`, which intentionally stays public so
unauthenticated callers can browse `accessControl.type == "public"` skills.

Non-owner reads of a skill the user cannot access return **404, not 403**,
to avoid leaking existence — see [auth-and-permissions.md](auth-and-permissions.md#api-route-protection).
Real 403s fire only on "can see but cannot modify" (PUT/DELETE).
"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import User, get_current_user
from db.chat_sessions import list_sessions_for_skill
from db.models import SkillConfig
from protocols.sessions_route import ListSessionsResponse, _to_summary
from skills import skill_config
from skills.platform import PLATFORM_OWNER_UID
from skills.slugify import slugify, unique_slug

router = APIRouter(prefix="/api/skills", tags=["skills"])


# === Request / Response models ===


class CreateSkillRequest(BaseModel):
    name: str
    slug: str | None = None
    description: str = ""
    instructions: str = ""
    display_name: str = Field(default="", alias="displayName")
    avatar: str = ""
    skill_metadata: dict = Field(default_factory=dict, alias="skillMetadata")
    access_control: dict = Field(default_factory=lambda: {"type": "private"}, alias="accessControl")
    protocols: dict | None = None
    initial_message: str = Field(default="", alias="initialMessage")
    tags: list[str] = []
    references: dict[str, str] = {}

    model_config = {"populate_by_name": True}


class UpdateSkillRequest(BaseModel):
    slug: str | None = None
    description: str | None = None
    instructions: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    avatar: str | None = None
    skill_metadata: dict | None = Field(default=None, alias="skillMetadata")
    access_control: dict | None = Field(default=None, alias="accessControl")
    protocols: dict | None = None
    initial_message: str | None = Field(default=None, alias="initialMessage")
    tags: list[str] | None = None
    references: dict[str, str] | None = None

    model_config = {"populate_by_name": True}


class SkillResponse(BaseModel):
    """Serialized skill for API responses."""

    skill_id: str = Field(alias="skillId")
    name: str
    slug: str | None = None
    description: str
    display_name: str = Field(alias="displayName")
    avatar: str
    instructions: str
    skill_metadata: dict = Field(alias="skillMetadata")
    access_control: dict = Field(alias="accessControl")
    owner_id: str = Field(alias="ownerId")
    owner_email: str = Field(alias="ownerEmail")
    protocols: dict
    initial_message: str = Field(alias="initialMessage")
    tags: list[str]
    featured: bool
    usage_count: int = Field(alias="usageCount")
    created_at: float = Field(alias="createdAt")
    updated_at: float = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_config(cls, config: SkillConfig) -> SkillResponse:
        data = config.model_dump(by_alias=True)
        return cls.model_validate(data)


# === Routes ===


@router.post("", status_code=201, response_model=SkillResponse)
def create_skill(req: CreateSkillRequest, user: User = Depends(get_current_user)) -> Any:  # noqa: B008
    """Create a new skill. `ownerId` is always set from the JWT — never client-supplied.

    Slug behaviour: if `slug` is omitted we derive one from `name` and silently
    suffix on collision (`-2`, `-3`, ...). If the client supplies `slug` and it
    collides, we still suffix silently — POST is the "I just want a skill, give
    me whatever URL" path; explicit slug edits go through PUT, which surfaces
    409 with a suggestion instead.
    """
    base = req.slug if req.slug else slugify(req.name)
    chosen_slug = unique_slug(user.uid, base)

    kwargs: dict[str, Any] = {"slug": chosen_slug}
    if req.skill_metadata:
        kwargs["skillMetadata"] = req.skill_metadata
    if req.access_control:
        kwargs["accessControl"] = req.access_control
    if req.protocols:
        kwargs["protocols"] = req.protocols
    if req.references:
        kwargs["references"] = req.references

    config = skill_config.create_skill(
        name=req.name,
        description=req.description,
        instructions=req.instructions,
        owner_id=user.uid,
        owner_email=user.email,
        displayName=req.display_name or req.name,
        avatar=req.avatar,
        initialMessage=req.initial_message,
        tags=req.tags,
        **kwargs,
    )
    return SkillResponse.from_config(config)


@router.get("", response_model=list[SkillResponse])
def list_skills(
    request: Request,
    owner_id: str | None = Query(None, alias="ownerId"),
    tag: str | None = None,
    access_type: str | None = Query(None, alias="accessType"),
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """List skills the caller can access.

    Implementation note: we currently fetch with the user-supplied filters
    (which may over- or under-return) and then drop anything the evaluator
    rejects. Correct, not optimally fast — a hot-path fan-out concern for
    1A.1b. Revisit with composite indexes once the list view becomes slow.
    """
    access = request.state.access
    configs = skill_config.list_skills(owner_id=owner_id, tag=tag, access_type=access_type, limit=limit)
    visible = [c for c in configs if access.can_access_skill(c)]
    return [SkillResponse.from_config(c) for c in visible]


@router.get("/marketplace", response_model=list[SkillResponse])
def list_marketplace(limit: int = Query(50, le=200)) -> Any:
    """List public skills for the marketplace. **Intentionally unauthenticated.**"""
    configs = skill_config.list_marketplace(limit=limit)
    return [SkillResponse.from_config(c) for c in configs]


@router.get("/by-slug/{owner_id}/{slug}", response_model=SkillResponse)
def get_skill_by_slug(
    owner_id: str,
    slug: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Resolve `(owner_id, slug)` -> skill, with the same access check as GET /{id}.

    Returns 404 (not 403) when the skill is missing or invisible to the caller,
    matching the UUID GET to avoid leaking existence via slug guessing.
    """
    config = skill_config.find_by_slug(owner_id, slug)
    if config is None or not request.state.access.can_access_skill(config):
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse.from_config(config)


@router.get("/{skill_id}", response_model=SkillResponse)
def get_skill(
    skill_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Get a skill by ID. Returns 404 (not 403) if the user cannot access it."""
    config = skill_config.get_skill(skill_id)
    if config is None or not request.state.access.can_access_skill(config):
        # Collapse "not found" and "not visible" into one response — don't leak existence.
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse.from_config(config)


@router.put("/{skill_id}", response_model=SkillResponse)
def update_skill(
    skill_id: str,
    req: UpdateSkillRequest,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Update a skill. Only the owner can modify; non-visible skills 404.

    Slug uniqueness is checked at the API layer: if the requested slug is
    already taken by another skill in the owner's namespace, returns 409
    with `{"error": "slug_taken", "suggestion": "<free-slug>"}`. Self-collision
    (saving the same slug back) is excluded.
    """
    updates = req.model_dump(by_alias=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    config = skill_config.get_skill(skill_id)
    if config is None or not request.state.access.can_access_skill(config):
        raise HTTPException(status_code=404, detail="Skill not found")
    # Platform-owned skills are read-only for everyone; fire this before
    # the owner check so the message points users at the fork endpoint.
    if config.owner_id == PLATFORM_OWNER_UID:
        raise HTTPException(status_code=403, detail="Platform-owned skills are read-only. Fork to customize.")
    if not request.state.access.is_skill_owner(config):
        # User can see it, just can't modify it → real 403.
        raise HTTPException(status_code=403, detail="Only the skill owner can update")

    if "slug" in updates:
        requested = updates["slug"]
        free = unique_slug(config.owner_id, requested, exclude_skill_id=skill_id)
        if free != requested:
            raise HTTPException(
                status_code=409,
                detail={"error": "slug_taken", "suggestion": free},
            )

    updated = skill_config.update_skill(skill_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillResponse.from_config(updated)


@router.delete("/{skill_id}", status_code=204)
def delete_skill(
    skill_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> None:
    """Delete a skill. Only the owner can delete; non-visible skills 404."""
    config = skill_config.get_skill(skill_id)
    if config is None or not request.state.access.can_access_skill(config):
        raise HTTPException(status_code=404, detail="Skill not found")
    if config.owner_id == PLATFORM_OWNER_UID:
        raise HTTPException(status_code=403, detail="Platform-owned skills are read-only. Fork to customize.")
    if not request.state.access.is_skill_owner(config):
        raise HTTPException(status_code=403, detail="Only the skill owner can delete")

    deleted = skill_config.delete_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.post("/{skill_id}/fork", status_code=201, response_model=SkillResponse)
def fork_skill(
    skill_id: str,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
) -> Any:
    """Fork a skill into a private copy owned by the caller.

    Works on any skill the caller can see — including platform-owned ones,
    which are otherwise read-only. 404 (not 403) if the source is invisible,
    so forking doesn't leak existence. The read-only guard doesn't apply:
    we're creating a new doc, not mutating the source.
    """
    source = skill_config.get_skill(skill_id)
    if source is None or not request.state.access.can_access_skill(source):
        raise HTTPException(status_code=404, detail="Skill not found")

    suffix = secrets.token_hex(3)[:6]
    new_skill = skill_config.create_skill(
        name=f"{source.name}-fork-{suffix}",
        description=source.description,
        instructions=source.instructions,
        owner_id=user.uid,
        owner_email=user.email,
        displayName=f"{source.display_name} (Fork)" if source.display_name else "",
        avatar=source.avatar,
        accessControl={"type": "private"},
        skillMetadata=source.skill_metadata.model_dump(by_alias=True),
        protocols=source.protocols.model_dump(by_alias=True),
        tags=list(source.tags),
        references=dict(source.references),
    )
    return SkillResponse.from_config(new_skill)


@router.get("/{skill_id}/sessions", response_model=ListSessionsResponse)
async def list_skill_sessions(
    skill_id: str,
    request: Request,
    cursor: str | None = Query(default=None),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),  # noqa: B008
) -> ListSessionsResponse:
    """List the caller's sessions for a skill, newest first.

    Returns only sessions owned by the authenticated caller — no cross-user
    session visibility. Returns 200 with an empty list when the caller has no
    sessions for this skill.
    """
    ctx = request.state.access
    sessions, next_cursor = list_sessions_for_skill(
        skill_id=skill_id,
        owner_uid=ctx.uid,
        page_size=page_size,
        cursor=cursor,
    )
    return ListSessionsResponse(
        sessions=[_to_summary(s, ctx.uid) for s in sessions],
        next_cursor=next_cursor,
    )
