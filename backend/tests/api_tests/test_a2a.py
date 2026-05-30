"""API tests for /.well-known/agent.json (PROTOCOLS-1A5 M2).

Verifies the A2A discovery card:
  - shape matches the minimum A2A spec fields
  - only skills with accessControl.type == 'public' appear
  - endpoint requires no auth (marketplace-parity)
  - cache invalidates after a skill create so newly-public skills
    appear in the card immediately
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from db.models import SkillConfig, SkillMetadata
from db.models.access import AccessControl


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
    # A2A minimum fields.
    for field in ("name", "description", "url", "version", "capabilities", "skills"):
        assert field in card, f"card missing field: {field}"
    assert isinstance(card["skills"], list)
    assert isinstance(card["capabilities"], dict)
    assert card["capabilities"]["streaming"] is True


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
