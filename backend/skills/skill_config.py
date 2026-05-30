"""Skill configuration — Firestore CRUD for skills collection.

All reads go through an in-memory cache (60s TTL) for hot skills.
Writes always go to Firestore and invalidate the cache entry.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from db import firestore as fs
from db.models import SkillConfig

COLLECTION = "skills"
_CACHE_TTL = 60  # seconds

# Simple in-memory cache: skill_id → (timestamp, SkillConfig)
_cache: dict[str, tuple[float, SkillConfig]] = {}


def _to_firestore(config: SkillConfig) -> dict[str, Any]:
    """Serialize a SkillConfig to a Firestore-compatible dict."""
    return config.model_dump(by_alias=True)


def _from_firestore(data: dict[str, Any]) -> SkillConfig:
    """Deserialize a Firestore document to a SkillConfig."""
    data.pop("__id", None)
    return SkillConfig.model_validate(data)


def _cache_get(skill_id: str) -> SkillConfig | None:
    entry = _cache.get(skill_id)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    if entry:
        del _cache[skill_id]
    return None


def _cache_set(skill_id: str, config: SkillConfig) -> None:
    _cache[skill_id] = (time.time(), config)


def _cache_invalidate(skill_id: str) -> None:
    _cache.pop(skill_id, None)
    # Any create/update/delete can flip a skill's public visibility, so
    # drop the A2A card snapshot and re-sync the MCP tool registry.
    # Function-local imports keep the skills package independent of
    # the protocols package at import time.
    from protocols.a2a import invalidate_cache as _invalidate_a2a_card
    from protocols.mcp_server import rebuild_tools as _rebuild_mcp_tools

    _invalidate_a2a_card()
    _rebuild_mcp_tools()


# === CRUD operations ===


def create_skill(
    name: str,
    description: str = "",
    instructions: str = "",
    owner_email: str = "",
    owner_id: str = "",
    **kwargs: Any,
) -> SkillConfig:
    """Create a new skill and persist to Firestore."""
    skill_id = str(uuid.uuid4())
    now = time.time()
    config = SkillConfig(
        skillId=skill_id,
        name=name,
        description=description,
        instructions=instructions,
        ownerEmail=owner_email,
        ownerId=owner_id,
        createdAt=now,
        updatedAt=now,
        **kwargs,
    )
    fs.set_document(COLLECTION, skill_id, _to_firestore(config))
    _cache_set(skill_id, config)
    # New public skills must appear in /.well-known/agent.json and /mcp
    # tools/list immediately — not after the 60s TTL.
    from protocols.a2a import invalidate_cache as _invalidate_a2a_card
    from protocols.mcp_server import rebuild_tools as _rebuild_mcp_tools

    _invalidate_a2a_card()
    _rebuild_mcp_tools()
    return config


def get_skill(skill_id: str) -> SkillConfig | None:
    """Get a skill by ID. Returns None if not found."""
    cached = _cache_get(skill_id)
    if cached:
        return cached

    data = fs.get_document(COLLECTION, skill_id)
    if data is None:
        return None

    config = _from_firestore(data)
    _cache_set(skill_id, config)
    return config


def find_by_slug(owner_id: str, slug: str) -> SkillConfig | None:
    """Resolve (owner_id, slug) -> SkillConfig via the composite index.

    Returns None if no skill with that slug exists in the owner's namespace.
    Caches the resolved config under its skill_id, so a follow-up `get_skill`
    after a slug-resolved fetch hits the cache.
    """
    docs = fs.query_documents(
        COLLECTION,
        filters=[("ownerId", "==", owner_id), ("slug", "==", slug)],
        limit=1,
    )
    if not docs:
        return None
    config = _from_firestore(docs[0])
    _cache_set(config.skill_id, config)
    return config


def update_skill(skill_id: str, updates: dict[str, Any]) -> SkillConfig | None:
    """Update specific fields on a skill. Returns updated config or None if not found."""
    existing = get_skill(skill_id)
    if existing is None:
        return None

    updates["updatedAt"] = time.time()
    fs.update_document(COLLECTION, skill_id, updates)
    _cache_invalidate(skill_id)

    # Re-read to get consistent state
    data = fs.get_document(COLLECTION, skill_id)
    if data is None:
        return None
    config = _from_firestore(data)
    _cache_set(skill_id, config)
    return config


def delete_skill(skill_id: str) -> bool:
    """Delete a skill. Returns True if it existed."""
    existing = get_skill(skill_id)
    if existing is None:
        return False

    fs.delete_document(COLLECTION, skill_id)
    _cache_invalidate(skill_id)
    return True


def list_skills(
    owner_id: str | None = None,
    tag: str | None = None,
    access_type: str | None = None,
    limit: int = 50,
) -> list[SkillConfig]:
    """List skills with optional filters."""
    filters: list[tuple[str, str, Any]] = []

    if owner_id:
        filters.append(("ownerId", "==", owner_id))
    if tag:
        filters.append(("tags", "array_contains", tag))
    if access_type:
        filters.append(("accessControl.type", "==", access_type))

    docs = fs.query_documents(
        COLLECTION,
        filters=filters if filters else None,
        order_by="updatedAt",
        order_direction="DESCENDING",
        limit=limit,
    )
    return [_from_firestore(doc) for doc in docs]


def list_marketplace(limit: int = 50) -> list[SkillConfig]:
    """List public skills for the marketplace, ordered by usage."""
    docs = fs.query_documents(
        COLLECTION,
        filters=[("accessControl.type", "==", "public")],
        order_by="usageCount",
        order_direction="DESCENDING",
        limit=limit,
    )
    return [_from_firestore(doc) for doc in docs]


def increment_usage(skill_id: str) -> None:
    """Atomically increment a skill's usage count."""
    fs.increment_field(COLLECTION, skill_id, "usageCount")
    _cache_invalidate(skill_id)
