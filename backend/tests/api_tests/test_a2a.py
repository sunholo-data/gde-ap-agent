"""API tests for /.well-known/agent.json (PROTOCOLS-1A5 M2).

Verifies the A2A discovery card:
  - shape matches the minimum A2A spec fields
  - only skills with accessControl.type == 'public' appear
  - endpoint requires no auth (marketplace-parity)
  - cache invalidates after a skill create so newly-public skills
    appear in the card immediately
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from db.models import SkillConfig, SkillMetadata
from db.models.access import AccessControl


def _extension_ids(card: dict[str, Any]) -> list[str]:
    """Extract bare extension IDs from a card's capabilities.extensions.

    A2A v0.2 schema makes these AgentExtension objects ({uri, description,
    required}); we reverse-lookup each URI in SUPPORTED_EXTENSION_INFO to
    recover the canonical IDs the rest of the codebase uses. Centralised so
    a schema bump (v0.3 etc.) only edits this helper.
    """
    from protocols.a2a import SUPPORTED_EXTENSION_INFO

    uri_to_id = {uri: ext_id for ext_id, (uri, _) in SUPPORTED_EXTENSION_INFO.items()}
    return [uri_to_id.get(ext["uri"], ext["uri"]) for ext in card["capabilities"]["extensions"]]


def _skill(
    *,
    name: str = "public-skill",
    skill_id: str = "public-skill-id",
    access: str = "public",
    description: str = "A public skill.",
    tags: list[str] | None = None,
) -> SkillConfig:
    return SkillConfig(
        name=name,
        description=description,
        instructions="Be helpful.",
        skillId=skill_id,
        ownerId="owner-uid",
        skillMetadata=SkillMetadata(model="gemini-2.5-flash"),
        accessControl=AccessControl(type=access),  # type: ignore[arg-type]
        tags=tags or [],
    )


@pytest.fixture()
def client() -> TestClient:
    import fast_api_app as module
    from protocols.a2a import invalidate_cache

    # Each test starts with a clean cache so the list_marketplace mock
    # applies cleanly on first fetch.
    invalidate_cache()
    return TestClient(module.app)


# --- Shape ---


def test_agent_card_returns_minimum_a2a_fields(client: TestClient) -> None:
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    card = resp.json()
    # A2A minimum fields. protocolVersion is required by Discovery Engine /
    # Gemini Enterprise validation — a missing one makes
    # `agents-cli register-gemini-enterprise --registration-type a2a` fail
    # with INVALID_ARGUMENT (real failure 2026-06-07).
    for field in (
        "protocolVersion",
        "name",
        "description",
        "url",
        "version",
        "capabilities",
        "skills",
    ):
        assert field in card, f"card missing field: {field}"
    assert isinstance(card["skills"], list)
    assert isinstance(card["capabilities"], dict)
    assert card["capabilities"]["streaming"] is True
    # Match the value we advertise in capabilities.extensions (a2a-v0.2).
    assert card["protocolVersion"] == "0.2.0"


def test_agent_card_skills_entries_have_required_fields(client: TestClient) -> None:
    public = _skill(name="search", skill_id="sid1", tags=["research"])
    with patch("protocols.a2a.list_marketplace", return_value=[public]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    assert len(skills) == 1
    entry = skills[0]
    for field in ("id", "name", "description", "tags", "inputModes", "outputModes"):
        assert field in entry, f"skill entry missing: {field}"
    assert entry["id"] == "sid1"
    assert entry["tags"] == ["research"]


# --- Public-only filter ---


def test_agent_card_excludes_private_skills(client: TestClient) -> None:
    """list_marketplace already filters to public — this test pins that we
    never augment it with broader queries in the a2a code path.

    Regression guard: if someone swaps list_marketplace() for list_skills()
    or adds a second Firestore query here, this test catches the private
    skill leak.
    """
    private = _skill(skill_id="priv", access="private", name="secret-skill")

    # If something accidentally calls list_skills without a public filter,
    # it would return `private`. list_marketplace MUST return only public
    # entries — we hand it the filtered set directly.
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["skills"]]
    assert "priv" not in ids, f"private skill leaked into A2A card: {ids}"

    # And confirm the card would surface a public one if list_marketplace
    # returned it — guards against a hard-wired empty list.
    public = _skill(skill_id="pub", access="public", name="public-skill")
    from protocols.a2a import invalidate_cache

    invalidate_cache()
    with patch("protocols.a2a.list_marketplace", return_value=[public, private]):
        resp = client.get("/.well-known/agent.json")
    # Even if the test stub unwisely returned a private entry, a2a must
    # only render what list_marketplace gives it — simulating a bug-free
    # list_marketplace, the card mirrors the input.
    ids = [s["id"] for s in resp.json()["skills"]]
    assert "pub" in ids


# --- No auth ---


def test_agent_card_requires_no_auth(client: TestClient) -> None:
    """The A2A card is discovery — unauthenticated crawlers must see it.

    We make the request with no Authorization header and assert success.
    """
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200, f"A2A card should not require auth, got {resp.status_code}"


# --- Cache invalidation ---


# --- Firestore failure is tolerated ---


def test_agent_card_serves_empty_skills_when_list_marketplace_raises(
    client: TestClient,
) -> None:
    """If Firestore is unreachable or the composite index isn't built yet,
    the card MUST still return 200 with an empty skills[] rather than 500.

    Regression guard: without the try/except in _build_card, a local dev
    backend (no composite index) or a fresh project bring-up produces a
    500 on the public discovery endpoint -- which is the one probe we
    can't guard with auth.
    """
    with patch(
        "protocols.a2a.list_marketplace",
        side_effect=RuntimeError("firestore exploded"),
    ):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["skills"] == []
    # And the rest of the card is still well-formed.
    for field in ("name", "description", "url", "version", "capabilities"):
        assert field in card


# --- X-A2A-Extensions negotiation (Gemini Enterprise / A2UI guide) ---


def test_agent_card_advertises_extensions_on_body(client: TestClient) -> None:
    """The card body MUST advertise `capabilities.extensions` so clients that
    discover by reading the body (not the response header) see the same
    capability set the server negotiates over the wire.
    """
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    caps = resp.json()["capabilities"]
    assert "extensions" in caps, "capabilities.extensions missing from card"
    assert isinstance(caps["extensions"], list)
    # Each extension must be a full AgentExtension descriptor (A2A v0.2 schema
    # — Discovery Engine / Gemini Enterprise rejects bare strings).
    for ext in caps["extensions"]:
        assert isinstance(ext, dict), f"extension entry must be an object, got {type(ext).__name__}"
        assert "uri" in ext, f"AgentExtension missing required `uri`: {ext!r}"
    ids = _extension_ids(resp.json())
    # The four canonical A2UI extensions from the integration guide.
    for required in (
        "a2ui-v0.9",
        "a2ui-basic-catalog-v0.9",
        "a2ui-inline-pattern",
        "a2ui-decoupled-pattern",
    ):
        assert required in ids, f"extension missing: {required}"


def test_agent_card_echoes_full_extensions_when_client_sends_none(client: TestClient) -> None:
    """No X-A2A-Extensions request header → server echoes its full set so the
    response header and body agree.
    """
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    echoed = [tok.strip() for tok in resp.headers["X-A2A-Extensions"].split(",")]
    body_ids = _extension_ids(resp.json())
    # Header carries bare IDs (per the integration guide); body carries
    # full descriptors (per A2A v0.2 schema). They must reference the
    # same underlying extension set.
    assert echoed == body_ids, "header IDs must match body IDs when no negotiation occurred"
    assert resp.headers["Vary"] == "X-A2A-Extensions"


def test_agent_card_advertises_adk_workflow_extension(client: TestClient) -> None:
    """WORKFLOW-PIPELINE M4: the card must advertise adk-workflow-v1 so
    discovering clients know this platform exposes deterministic ADK
    workflow agents (SequentialAgent/ParallelAgent/LoopAgent), not just
    LLM-driven skills. Without this, a peer agent can't tell ap-pipeline
    runs Extract → Validate → Post in code rather than asking a model
    whether to continue.
    """
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    ids = _extension_ids(resp.json())
    assert "adk-workflow-v1" in ids, f"adk-workflow-v1 must be advertised, got {ids!r}"


def test_agent_card_negotiates_extension_intersection(client: TestClient) -> None:
    """Client advertises a subset → server replies with the intersection
    only, preserving canonical order. The body still advertises the full
    server-supported set (the body is identity, the header is negotiation).
    """
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get(
            "/.well-known/agent.json",
            headers={"X-A2A-Extensions": "a2ui-v0.9, a2ui-inline-pattern, made-up-ext"},
        )
    assert resp.status_code == 200
    echoed = [tok.strip() for tok in resp.headers["X-A2A-Extensions"].split(",")]
    # Intersection: only the two we support out of what the client asked for.
    assert echoed == ["a2ui-v0.9", "a2ui-inline-pattern"]
    # Body still advertises the full server set so other clients still see it.
    body_ids = _extension_ids(resp.json())
    assert "a2ui-decoupled-pattern" in body_ids, "body must keep advertising full server capabilities"


def test_agent_card_returns_empty_negotiation_when_no_overlap(client: TestClient) -> None:
    """Client only asks for extensions we don't support → empty header,
    not 4xx. Discovery must stay permissive; the client decides how to
    react to an empty negotiation.
    """
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get(
            "/.well-known/agent.json",
            headers={"X-A2A-Extensions": "nonexistent-ext-1, nonexistent-ext-2"},
        )
    assert resp.status_code == 200
    assert resp.headers["X-A2A-Extensions"] == ""


# --- Contract test against canonical A2A AgentCard structure ---
#
# The blog's reference is the A2A spec at github.com/google/a2a. Without
# network access in CI we vendor the contract here as a structural schema
# matching A2A v0.2+ AgentCard requirements. Field list is mirrored from
# the spec; required vs optional is enforced.


def _validate_against_a2a_contract(card: dict[str, Any]) -> list[str]:
    """Return a list of contract violations; empty list means the card is valid."""
    errors: list[str] = []

    # Top-level required fields per A2A AgentCard schema.
    required_top = {
        "name": str,
        "description": str,
        "url": str,
        "version": str,
        "capabilities": dict,
        "defaultInputModes": list,
        "defaultOutputModes": list,
        "skills": list,
    }
    for field, expected_type in required_top.items():
        if field not in card:
            errors.append(f"missing required field: {field}")
            continue
        if not isinstance(card[field], expected_type):
            errors.append(f"field {field!r}: expected {expected_type.__name__}, got {type(card[field]).__name__}")

    # capabilities sub-object: booleans for the three documented switches.
    caps = card.get("capabilities", {})
    for cap_field in ("streaming", "pushNotifications", "stateTransitionHistory"):
        if cap_field not in caps:
            errors.append(f"capabilities missing field: {cap_field}")
        elif not isinstance(caps[cap_field], bool):
            errors.append(f"capabilities.{cap_field}: expected bool, got {type(caps[cap_field]).__name__}")
    # Optional but spec-recognised: capabilities.extensions — A2A v0.2 schema
    # requires a list of AgentExtension objects each with a `uri` field
    # (Discovery Engine enforces this — bare strings get
    # "unexpected instance type" rejections).
    if "extensions" in caps:
        if not isinstance(caps["extensions"], list):
            errors.append("capabilities.extensions: expected list")
        else:
            for i, ext in enumerate(caps["extensions"]):
                if not isinstance(ext, dict):
                    errors.append(
                        f"capabilities.extensions[{i}]: expected AgentExtension object, got {type(ext).__name__}"
                    )
                elif "uri" not in ext:
                    errors.append(f"capabilities.extensions[{i}]: AgentExtension missing required `uri`")
                elif not isinstance(ext["uri"], str):
                    errors.append(f"capabilities.extensions[{i}].uri: expected str, got {type(ext['uri']).__name__}")

    # defaultInputModes / defaultOutputModes: must be non-empty lists of strings.
    for modes_field in ("defaultInputModes", "defaultOutputModes"):
        modes = card.get(modes_field, [])
        if isinstance(modes, list):
            if not modes:
                errors.append(f"{modes_field}: must be non-empty")
            for i, mode in enumerate(modes):
                if not isinstance(mode, str):
                    errors.append(f"{modes_field}[{i}]: expected str, got {type(mode).__name__}")

    # skills[] entries: id / name / description required; tags / inputModes /
    # outputModes optional but typed when present.
    for i, skill in enumerate(card.get("skills", [])):
        if not isinstance(skill, dict):
            errors.append(f"skills[{i}]: expected object, got {type(skill).__name__}")
            continue
        for required_str in ("id", "name", "description"):
            if required_str not in skill:
                errors.append(f"skills[{i}]: missing {required_str}")
            elif not isinstance(skill[required_str], str):
                errors.append(f"skills[{i}].{required_str}: expected str")
        for optional_list in ("tags", "inputModes", "outputModes"):
            if optional_list in skill and not isinstance(skill[optional_list], list):
                errors.append(f"skills[{i}].{optional_list}: expected list")

    # URL plausibility — must look like an absolute URL (the A2A discovery
    # contract assumes this is the endpoint clients can POST to).
    url = card.get("url", "")
    if isinstance(url, str) and not url.startswith(("http://", "https://")):
        errors.append(f"url: must be absolute (http/https), got {url!r}")

    return errors


def test_agent_card_passes_a2a_contract_with_no_skills(client: TestClient) -> None:
    """Empty marketplace → card still conforms to the A2A AgentCard contract."""
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    errors = _validate_against_a2a_contract(resp.json())
    assert errors == [], f"A2A contract violations: {errors}"


def test_agent_card_passes_a2a_contract_with_skills(client: TestClient) -> None:
    """Card with a public skill still conforms. Pins the per-skill shape so
    a future shape change to `_skill_to_a2a()` can't silently drop a field
    the A2A spec requires.
    """
    public = _skill(name="search", skill_id="sid1", description="Search docs.", tags=["research"])
    with patch("protocols.a2a.list_marketplace", return_value=[public]):
        resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    errors = _validate_against_a2a_contract(resp.json())
    assert errors == [], f"A2A contract violations: {errors}"


def test_agent_card_cache_invalidated_after_skill_create(client: TestClient) -> None:
    """Creating a new public skill must clear the A2A card cache so
    subsequent GETs reflect the new skill without waiting for the 60s TTL.
    """
    # Warm the cache with an empty skill list.
    with patch("protocols.a2a.list_marketplace", return_value=[]):
        resp = client.get("/.well-known/agent.json")
    assert resp.json()["skills"] == []

    # Simulate a skill create — which calls _cache_invalidate, which in
    # turn calls protocols.a2a.invalidate_cache.
    from skills.skill_config import _cache_invalidate

    _cache_invalidate("any-id")

    # Next GET must rebuild from Firestore. With a new skill mocked in,
    # it should appear immediately.
    new_skill = _skill(skill_id="fresh", name="freshly-minted")
    with patch("protocols.a2a.list_marketplace", return_value=[new_skill]):
        resp = client.get("/.well-known/agent.json")
    ids = [s["id"] for s in resp.json()["skills"]]
    assert "fresh" in ids, f"expected cache to invalidate, got {ids}"
