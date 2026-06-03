"""A2A agent card at /.well-known/agent.json.

Workshop W4 — A2A: Getting Found
  The whole file is ~120 lines. The business logic is `_skill_to_a2a()` and
  `agent_card()` — about 15 lines. The rest is the time-bucket cache that
  avoids a Firestore read on every crawler hit. Point out `_time_bucket()`
  as the pattern: no scheduler, no background thread, just a rotating lru_cache key.

Unauthenticated discovery endpoint that advertises this platform's
*public* skills to other A2A-compliant agents. Matches marketplace
semantics: if a skill is listed in the public marketplace, it's listed
here too; everything else stays invisible.

Not a full A2A task-handler — that's a follow-up. This is the discovery
surface, cached for 60s so crawlers don't hammer Firestore.

See https://github.com/google/a2a for the protocol.
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Header, Response

from skills.skill_config import list_marketplace

if TYPE_CHECKING:
    from db.models import SkillConfig

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache TTL in seconds — keeps the card warm for crawlers without
# pinning a stale snapshot for more than a minute. list_marketplace()
# is a Firestore query; 60s is the sweet spot between cost and freshness.
_CACHE_TTL = 60.0

# A2A extensions this agent supports. Advertised on the card body
# (`capabilities.extensions`) and echoed in the `X-A2A-Extensions` response
# header per the Gemini Enterprise / A2UI integration guide. Clients send
# `X-A2A-Extensions` listing what they can render; the server replies with
# the intersection so both sides know which pattern/catalog to use.
#
# - a2ui-v0.9 — A2UI message protocol, v0.9 wire format
# - a2ui-basic-catalog-v0.9 — pre-approved BasicCatalog (Card, Text, Button,
#   Image, Column, Row, Divider, ChoicePicker, …) per a2ui.org spec
# - a2ui-inline-pattern — component tree with data inlined (createSurface +
#   updateComponents only); the default GE-compatible pattern
# - a2ui-decoupled-pattern — component tree + updateDataModel as separate
#   messages, enabling token-efficient mid-stream data refreshes
# - a2a-v0.2 — A2A discovery card schema version
# - mcp-apps-v1 — sandboxed iframe surface for third-party UI artefacts
# - adk-workflow-v1 — this agent exposes deterministic ADK workflow agents
#   (SequentialAgent/ParallelAgent/LoopAgent) where the control flow is
#   code, not a model. Discovery clients can rely on the named pipeline
#   skills (ap-pipeline) running their sub_skills in declared order.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    "a2ui-v0.9",
    "a2ui-basic-catalog-v0.9",
    "a2ui-inline-pattern",
    "a2ui-decoupled-pattern",
    "a2a-v0.2",
    "mcp-apps-v1",
    "adk-workflow-v1",
)


def _parse_client_extensions(header_value: str | None) -> list[str]:
    """Parse the `X-A2A-Extensions` request header into a clean list.

    Per the integration guide, clients advertise their renderer capabilities
    as a comma-separated list. We tolerate whitespace and empty entries so
    a misformatted header doesn't drop the request — discovery must stay
    permissive.
    """
    if not header_value:
        return []
    return [tok.strip() for tok in header_value.split(",") if tok.strip()]


def _negotiate_extensions(client_extensions: list[str]) -> list[str]:
    """Return the intersection of client- and server-supported extensions.

    Empty client list (no header) → echo the full server set so clients
    using the body's `capabilities.extensions` see the same value as the
    response header. Non-empty client list → intersect, preserving the
    canonical server order for deterministic test output.
    """
    if not client_extensions:
        return list(SUPPORTED_EXTENSIONS)
    return [ext for ext in SUPPORTED_EXTENSIONS if ext in client_extensions]


def _skill_to_a2a(skill: SkillConfig) -> dict[str, Any]:
    """Convert a SkillConfig to the A2A skills[] entry shape."""
    return {
        "id": skill.skill_id,
        "name": skill.display_name or skill.name,
        "description": skill.description,
        "tags": list(skill.tags),
        # A2A is modality-flexible; we handle text in and text + A2UI
        # (JSON in fenced blocks) out. Keeping this narrow — extend when
        # we actually start serving audio/image inputs via A2A.
        "inputModes": ["text"],
        "outputModes": ["text"],
    }


def _build_card(base_url: str) -> dict[str, Any]:
    """Generate the A2A card from the current public skill set.

    If Firestore is unreachable or the composite marketplace index
    hasn't built yet, we serve an empty skills[] rather than 500-ing
    the card: discovery stays working even when the catalogue isn't.
    """
    try:
        skills = list_marketplace(limit=100)
    except Exception:
        logger.exception("a2a._build_card: list_marketplace failed; serving empty skills")
        skills = []
    return {
        # User-visible card identity. Downstream forks override via the
        # A2A_AGENT_NAME / A2A_AGENT_DESCRIPTION env vars (default:
        # upstream Sunholo branding). Mirrors the frontend BRANDING
        # constant's appName + description (kept in sync manually for
        # now — a small follow-up could centralise via a backend
        # BRANDING module).
        "name": os.getenv("A2A_AGENT_NAME", "Sunholo AI Protocol Platform"),
        "description": os.getenv(
            "A2A_AGENT_DESCRIPTION",
            "Open-source AI protocol platform — Skills + AG-UI + A2UI + MCP Apps + A2A on Google ADK.",
        ),
        "url": base_url,
        "version": "6.0.0",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": False,
            # A2A extensions this agent supports. Mirrored in the
            # `X-A2A-Extensions` response header so a client that does
            # capability negotiation by header (per the GE / A2UI
            # integration guide) and a client that reads the card body
            # see the same set.
            "extensions": list(SUPPORTED_EXTENSIONS),
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [_skill_to_a2a(s) for s in skills],
    }


# --- Cache ---
# lru_cache on a timestamped key: mod the timestamp to _CACHE_TTL so the
# key rotates once per TTL window, giving us time-bounded caching without
# a scheduler. Call sites pass `_time_bucket()` as the cache key.


def _time_bucket() -> int:
    return int(time.time() // _CACHE_TTL)


@lru_cache(maxsize=4)
def _cached_card(base_url: str, bucket: int) -> dict[str, Any]:
    # `bucket` is part of the cache key only — it forces cache invalidation
    # when the 60s window rolls over. It isn't used inside the body.
    del bucket
    return _build_card(base_url)


def invalidate_cache() -> None:
    """Force the next /.well-known/agent.json hit to rebuild from Firestore.

    Called by skill CRUD routes after create/update/delete so the card
    reflects the new public skill set without waiting for the 60s TTL.
    """
    _cached_card.cache_clear()


# --- Route ---


@router.get("/.well-known/agent.json")
def agent_card(
    response: Response,
    x_a2a_extensions: Annotated[str | None, Header(alias="X-A2A-Extensions")] = None,
) -> dict[str, Any]:
    """A2A agent card. Unauthenticated — advertises public skills only.

    Private / domain / specific / tagged skills never appear here: the
    `list_marketplace()` query filters on `accessControl.type == "public"`.

    A2UI capability negotiation
    ---------------------------
    Per the Gemini Enterprise / A2UI integration guide
    (cloud.google.com/blog/.../guide-to-gemini-enterprise-and-a2ui-integration),
    A2A clients advertise renderer capabilities via the `X-A2A-Extensions`
    request header. We negotiate the intersection with our own
    `SUPPORTED_EXTENSIONS` and return the result on the response header so
    the client knows which patterns the agent will emit.

    The `Vary: X-A2A-Extensions` header is set so any HTTP cache between
    the client and the agent keys responses by capability set instead of
    serving a stale set to a differently-capable client.
    """
    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:1956")
    negotiated = _negotiate_extensions(_parse_client_extensions(x_a2a_extensions))
    response.headers["X-A2A-Extensions"] = ", ".join(negotiated)
    response.headers["Vary"] = "X-A2A-Extensions"
    return _cached_card(base_url, _time_bucket())
