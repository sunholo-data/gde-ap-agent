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

Pairs with `protocols.a2a_invocation` which mounts ADK's `to_a2a()`
Starlette adapter at `/a2a` to handle JSON-RPC `message/send` etc.
The card produced here advertises `url = <base>/a2a` so peers know
where to POST. The dict-shaped card is what we serve on the wire;
the AgentCard-shaped card is what we hand to ADK via `to_a2a(agent_card=)`
so the same canonical source of truth feeds both surfaces.

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
# A2A extensions this agent supports. Single source of truth keyed by the
# extension ID — the header uses just the IDs (per the integration guide),
# the card body needs full AgentExtension descriptors (per A2A v0.2 schema,
# enforced by Discovery Engine / Gemini Enterprise — emitting bare strings
# fails registration with "unexpected instance type" at
# /capabilities/extensions/N. Real failure 2026-06-07.)
SUPPORTED_EXTENSION_INFO: dict[str, tuple[str, str]] = {
    "a2ui-v0.9": (
        "https://github.com/agentic-protocols/a2ui/blob/main/spec/v0.9.md",
        "A2UI v0.9 declarative UI surfaces",
    ),
    "a2ui-basic-catalog-v0.9": (
        "https://github.com/agentic-protocols/a2ui/blob/main/spec/basic-catalog-v0.9.md",
        "A2UI BasicCatalog component set",
    ),
    "a2ui-inline-pattern": (
        "https://github.com/agentic-protocols/a2ui/blob/main/spec/inline-pattern.md",
        "A2UI inline-rendered surfaces (in-chat)",
    ),
    "a2ui-decoupled-pattern": (
        "https://github.com/agentic-protocols/a2ui/blob/main/spec/decoupled-pattern.md",
        "A2UI decoupled surfaces (separate pane)",
    ),
    "a2a-v0.2": (
        "https://a2aproject.github.io/A2A/v0.2",
        "A2A protocol v0.2 (this card complies with this version)",
    ),
    "mcp-apps-v1": (
        "https://modelcontextprotocol.io/specification/draft/server/apps",
        "MCP Apps v1 sandboxed iframe artefacts",
    ),
    "adk-workflow-v1": (
        "https://google.github.io/adk-docs/agents/workflow-agents/",
        "ADK workflow agents (SequentialAgent / ParallelAgent / LoopAgent)",
    ),
}

# Canonical ID list — derived so any new extension only needs adding to
# the info dict above (single source of truth, no parallel arrays to
# drift). Public callers still use this as the iteration order.
SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(SUPPORTED_EXTENSION_INFO.keys())


def _extension_descriptor(ext_id: str) -> dict[str, Any]:
    """Wrap a supported extension ID as an A2A AgentExtension object.

    Falls back to a synthetic urn:-style URI if the ID is somehow missing
    from the info table — defence in depth so a fork adding a new extension
    without remembering to update SUPPORTED_EXTENSION_INFO still produces a
    card that passes schema validation rather than crashing the endpoint.
    """
    uri, description = SUPPORTED_EXTENSION_INFO.get(
        ext_id,
        (f"urn:sunholo:a2a-extension:{ext_id}", ext_id),
    )
    return {"uri": uri, "description": description, "required": False}


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


# A2A JSON-RPC invocation surface mount point. The card's `url` field must
# point HERE so peers know where to POST `message/send` requests. The
# discovery card itself stays at `/.well-known/agent.json` (root); only the
# `url` field changes. Keep in sync with the `app.mount("/a2a", ...)` call
# in fast_api_app.py.
A2A_INVOCATION_PATH = "/a2a"


def _build_card_dict(base_url: str) -> dict[str, Any]:
    """Generate the A2A card from the current public skill set.

    Returns the wire-shape dict served at `/.well-known/agent.json`. The
    `url` field advertises the A2A JSON-RPC invocation endpoint at
    `<base>/a2a` (where ADK's `to_a2a()` is mounted — see
    `protocols.a2a_invocation`); the discovery card itself remains at the
    root well-known path. Peers GET the card from one URL and POST
    `message/send` to the other.

    If Firestore is unreachable or the composite marketplace index
    hasn't built yet, we serve an empty skills[] rather than 500-ing
    the card: discovery stays working even when the catalogue isn't.
    """
    try:
        skills = list_marketplace(limit=100)
    except Exception:
        logger.exception("a2a._build_card_dict: list_marketplace failed; serving empty skills")
        skills = []
    return {
        # A2A wire-protocol version this card complies with. Required by
        # the Discovery Engine / Gemini Enterprise card validator — a
        # missing protocolVersion makes `agents-cli register-gemini-enterprise
        # --registration-type a2a` fail with INVALID_ARGUMENT. Matches the
        # `a2a-v0.2` value we advertise in `capabilities.extensions`.
        "protocolVersion": "0.2.0",
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
        # NOT base_url. Peers use `url` to POST invocations, and ADK's
        # `to_a2a()` mount handles those at /a2a — see A2A_INVOCATION_PATH.
        "url": f"{base_url.rstrip('/')}{A2A_INVOCATION_PATH}",
        "version": "6.0.0",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": False,
            # A2A extensions this agent supports, as full AgentExtension
            # descriptors per A2A v0.2 schema (uri + description + required).
            # Discovery Engine / Gemini Enterprise rejects bare-string
            # extension entries — caught 2026-06-07 during a real
            # `agents-cli register-gemini-enterprise` attempt with:
            #   "At /capabilities/extensions/0 of \"a2ui-v0.9\" - unexpected
            #    instance type"
            # The negotiation HEADER still carries bare IDs (per the
            # integration guide); only the body needs descriptors.
            "extensions": [_extension_descriptor(ext) for ext in SUPPORTED_EXTENSIONS],
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [_skill_to_a2a(s) for s in skills],
    }


def _build_card_model(base_url: str) -> Any:
    """Generate the A2A card as ADK's `AgentCard` pydantic model.

    This is what we pass to `to_a2a(agent_card=...)` so the mounted
    A2A surface advertises the SAME card as `/.well-known/agent.json` —
    no drift between what peers discover at the well-known path and what
    ADK's auto-built card would produce. Pydantic does the wire validation
    for free; if our dict's shape is wrong we find out at construction
    time, not at a peer's first request.

    Import deferred to call time because `a2a.types` is part of the
    `a2a-sdk` dep that ships with `google-adk`; keeping the import local
    avoids loading the whole A2A SDK when only the discovery card is
    needed (the `/.well-known/agent.json` path stays light).
    """
    from a2a.types import AgentCard

    return AgentCard.model_validate(_build_card_dict(base_url))


# Backwards-compatible alias for callers that still import `_build_card`.
# The wire shape (dict) is the original contract; the model variant is new.
_build_card = _build_card_dict


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
    return _build_card_dict(base_url)


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
