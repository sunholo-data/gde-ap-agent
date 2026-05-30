"""Request-scoped access context + pure-Python 5-type access evaluator.

`AccessContext` is built **once per request** in `get_current_user` (see
`auth/firebase_auth.py`) and stored on `request.state.access`. Route
handlers — and later the agent's tool_context — then check access against
in-memory state; no Firestore reads on the hot path.

Evaluator rules (from resource-access-control.md:169):

    - public   → always True
    - owner    → always True (owner wins regardless of type)
    - private  → only owner (handled by the rule above)
    - domain   → user.domain == ac.domain
    - specific → user.email in ac.emails
    - tagged   → user.group_tags intersects ac.tags (frozenset set-intersection)

Typed protocol `_HasAccess` is used instead of importing `SkillConfig`
directly so `access_context.py` has no dependency on `db.models` — keeps
the evaluator reusable for future resource types (buckets, folders, chat
sessions) without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from auth.firebase_auth import User
    from db.models.access import AccessControl


@runtime_checkable
class _HasAccess(Protocol):
    """Minimal resource protocol: an access_control block and an owner_id."""

    access_control: AccessControl
    owner_id: str


@dataclass(frozen=True)
class AccessContext:
    """Immutable per-request access snapshot derived from a verified Firebase JWT.

    Held on `request.state.access` after `get_current_user` completes. All
    downstream access checks read from this; none re-read the JWT or
    Firestore.
    """

    uid: str
    email: str = ""
    domain: str = ""
    group_tags: frozenset[str] = field(default_factory=frozenset)

    # --- Resource checks (generic) -----------------------------------------

    def is_owner(self, resource: _HasAccess) -> bool:
        """True iff the user owns the resource."""
        return bool(resource.owner_id) and resource.owner_id == self.uid

    def can_access(self, resource: _HasAccess) -> bool:
        """Apply the 5-type evaluator to any resource with access_control + owner_id."""
        return can_access(resource.access_control, self, resource.owner_id)

    # --- Skill-specific shims (keep callsites readable) --------------------

    def can_access_skill(self, skill: _HasAccess) -> bool:
        """Alias of `can_access` for skill-route callsites."""
        return self.can_access(skill)

    def is_skill_owner(self, skill: _HasAccess) -> bool:
        """Alias of `is_owner` for skill-route callsites."""
        return self.is_owner(skill)

    # --- Folder-specific shim ---------------------------------------------
    # Folders carry `effective_access` (pre-computed at write time) rather
    # than `access_control`, so the generic `_HasAccess` protocol doesn't fit.

    def can_access_folder(self, folder: object) -> bool:
        """Apply the 5-type evaluator to a folder's pre-computed effectiveAccess."""
        ac = getattr(folder, "effective_access", None)
        owner_id = getattr(folder, "owner_id", "")
        if ac is None:
            return False
        return can_access(ac, self, owner_id)


def build_access_context(user: User) -> AccessContext:
    """Construct `AccessContext` from a verified `User`. Called once per request."""
    return AccessContext(
        uid=user.uid,
        email=user.email,
        domain=user.domain,
        group_tags=user.group_tags,
    )


def can_access(ac: AccessControl, ctx: AccessContext, owner_id: str) -> bool:
    """Pure 5-type evaluator — no I/O, no Firestore reads, no JWT lookups.

    See resource-access-control.md for the canonical rule table.
    """
    if ac.type == "public":
        return True
    if owner_id and owner_id == ctx.uid:  # owner always wins
        return True
    if ac.type == "domain":
        return bool(ctx.domain) and ctx.domain == ac.domain
    if ac.type == "specific":
        return bool(ctx.email) and ctx.email in (ac.emails or [])
    if ac.type == "tagged":
        return bool(ctx.group_tags & set(ac.tags or []))
    # private and not owner (or unknown type — deny)
    return False


__all__ = ["AccessContext", "build_access_context", "can_access"]
