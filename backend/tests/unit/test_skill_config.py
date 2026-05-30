"""Unit tests for skill CRUD service with mocked Firestore."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from db.models import SkillConfig
from skills import skill_config


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the in-memory cache before each test."""
    skill_config._cache.clear()
    yield
    skill_config._cache.clear()


@pytest.fixture()
def mock_fs():
    """Patch the firestore module used by skill_config."""
    with patch.object(skill_config, "fs") as mock:
        yield mock


def _sample_data(**overrides) -> dict:
    defaults = {
        "skillId": "abc-123",
        "name": "test-skill",
        "description": "A test skill.",
        "instructions": "Help with tests.",
        "skillMetadata": {"author": "aitana", "version": "1.0", "model": "gemini-2.5-flash"},
        "references": {},
        "assets": {},
        "displayName": "Test Skill",
        "avatar": "",
        "ownerEmail": "mark@aitana.ai",
        "ownerId": "user-1",
        "accessControl": {"type": "private"},
        "protocols": {
            "mcp": {"enabled": False},
            "a2a": {"enabled": False},
            "agui": {"enabled": True},
            "a2ui": {"enabled": False},
            "mcpApps": {"enabled": False},
        },
        "initialMessage": "",
        "tags": [],
        "featured": False,
        "usageCount": 0,
        "createdAt": 1000.0,
        "updatedAt": 1000.0,
        "v5AssistantId": None,
    }
    defaults.update(overrides)
    return defaults


# === create_skill ===


def test_create_skill(mock_fs):
    config = skill_config.create_skill(
        name="my-skill",
        description="Does things.",
        owner_email="mark@aitana.ai",
        owner_id="user-1",
    )
    assert isinstance(config, SkillConfig)
    assert config.name == "my-skill"
    assert config.owner_email == "mark@aitana.ai"
    mock_fs.set_document.assert_called_once()
    # Should be cached
    assert config.skill_id in skill_config._cache


# === get_skill ===


def test_get_skill_from_firestore(mock_fs):
    mock_fs.get_document.return_value = _sample_data()
    config = skill_config.get_skill("abc-123")
    assert config is not None
    assert config.name == "test-skill"
    mock_fs.get_document.assert_called_once_with("skills", "abc-123")


def test_get_skill_not_found(mock_fs):
    mock_fs.get_document.return_value = None
    config = skill_config.get_skill("nonexistent")
    assert config is None


def test_get_skill_cache_hit(mock_fs):
    """Second get should use cache, not Firestore."""
    mock_fs.get_document.return_value = _sample_data()
    skill_config.get_skill("abc-123")
    skill_config.get_skill("abc-123")
    # Only one Firestore call — second was cached
    assert mock_fs.get_document.call_count == 1


def test_find_by_slug_returns_config(mock_fs):
    mock_fs.query_documents.return_value = [_sample_data(slug="general-assistant")]
    config = skill_config.find_by_slug("user-1", "general-assistant")
    assert config is not None
    assert config.slug == "general-assistant"
    mock_fs.query_documents.assert_called_once_with(
        "skills",
        filters=[("ownerId", "==", "user-1"), ("slug", "==", "general-assistant")],
        limit=1,
    )


def test_find_by_slug_returns_none_when_missing(mock_fs):
    mock_fs.query_documents.return_value = []
    assert skill_config.find_by_slug("user-1", "missing") is None


def test_find_by_slug_caches_resolved_skill(mock_fs):
    """Slug lookup caches under skill_id so a follow-up get_skill is a cache hit."""
    mock_fs.query_documents.return_value = [_sample_data()]
    skill_config.find_by_slug("user-1", "test-skill")
    # Second call to get_skill should hit cache, not Firestore.
    mock_fs.get_document.return_value = _sample_data()
    skill_config.get_skill("abc-123")
    mock_fs.get_document.assert_not_called()


def test_get_skill_cache_expiry(mock_fs):
    """Cache entry should expire after TTL, triggering a fresh Firestore read."""
    mock_fs.get_document.return_value = _sample_data()
    skill_config.get_skill("abc-123")
    assert mock_fs.get_document.call_count == 1

    # Simulate TTL expiry by backdating the cache timestamp
    cache_entry = skill_config._cache["abc-123"]
    skill_config._cache["abc-123"] = (cache_entry[0] - skill_config._CACHE_TTL - 1, cache_entry[1])

    skill_config.get_skill("abc-123")
    # Should have made a second Firestore call after expiry
    assert mock_fs.get_document.call_count == 2


# === update_skill ===


def test_update_skill(mock_fs):
    mock_fs.get_document.return_value = _sample_data()
    updated = skill_config.update_skill("abc-123", {"displayName": "Updated Name"})
    assert updated is not None
    mock_fs.update_document.assert_called_once()
    # Verify updatedAt was added
    call_args = mock_fs.update_document.call_args[0][2]
    assert "updatedAt" in call_args


def test_update_skill_not_found(mock_fs):
    mock_fs.get_document.return_value = None
    result = skill_config.update_skill("nonexistent", {"displayName": "X"})
    assert result is None
    mock_fs.update_document.assert_not_called()


# === delete_skill ===


def test_delete_skill(mock_fs):
    mock_fs.get_document.return_value = _sample_data()
    result = skill_config.delete_skill("abc-123")
    assert result is True
    mock_fs.delete_document.assert_called_once_with("skills", "abc-123")


def test_delete_skill_not_found(mock_fs):
    mock_fs.get_document.return_value = None
    result = skill_config.delete_skill("nonexistent")
    assert result is False
    mock_fs.delete_document.assert_not_called()


# === list_skills ===


def test_list_skills_no_filters(mock_fs):
    mock_fs.query_documents.return_value = [_sample_data()]
    results = skill_config.list_skills()
    assert len(results) == 1
    assert results[0].name == "test-skill"
    mock_fs.query_documents.assert_called_once()


def test_list_skills_by_owner(mock_fs):
    mock_fs.query_documents.return_value = [_sample_data()]
    skill_config.list_skills(owner_id="user-1")
    call_filters = mock_fs.query_documents.call_args[1]["filters"]
    assert ("ownerId", "==", "user-1") in call_filters


def test_list_skills_by_tag(mock_fs):
    mock_fs.query_documents.return_value = []
    skill_config.list_skills(tag="extraction")
    call_filters = mock_fs.query_documents.call_args[1]["filters"]
    assert ("tags", "array_contains", "extraction") in call_filters


def test_list_skills_by_access_type(mock_fs):
    mock_fs.query_documents.return_value = []
    skill_config.list_skills(access_type="public")
    call_filters = mock_fs.query_documents.call_args[1]["filters"]
    assert ("accessControl.type", "==", "public") in call_filters


# === list_marketplace ===


def test_list_marketplace(mock_fs):
    mock_fs.query_documents.return_value = [_sample_data(accessControl={"type": "public"}, usageCount=42)]
    results = skill_config.list_marketplace()
    assert len(results) == 1
    mock_fs.query_documents.assert_called_once()
    call_kwargs = mock_fs.query_documents.call_args[1]
    assert call_kwargs["order_by"] == "usageCount"


# === increment_usage ===


def test_increment_usage(mock_fs):
    skill_config.increment_usage("abc-123")
    mock_fs.increment_field.assert_called_once_with("skills", "abc-123", "usageCount")
