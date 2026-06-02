"""Unit tests for skills.structured_invocation — Audit View standalone runs."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from db.models import SkillConfig
from skills.skill_processor import SkillNotFoundError
from skills.structured_invocation import (
    StructuredInputInvalidError,
    StructuredInputNotSupportedError,
    serialize_input_as_message,
    validate_structured_input,
)


def _make_skill_with_schema(schema: dict | None) -> SkillConfig:
    metadata = {
        "author": "test",
        "version": "1.0",
        "model": "gemini-2.5-flash",
        "tools": [],
        "toolConfigs": {},
        "subSkills": [],
    }
    if schema is not None:
        metadata["structuredInput"] = schema
    return SkillConfig(
        skillId="test-skill",
        name="test-skill",
        description="A test specialist skill.",
        instructions="Test instructions.",
        displayName="Test",
        ownerEmail="t@e.com",
        ownerId="u1",
        skillMetadata=metadata,
    )


def test_validate_passes_with_well_formed_input():
    schema = {
        "type": "object",
        "properties": {"document_id": {"type": "string", "minLength": 1}},
        "required": ["document_id"],
        "additionalProperties": False,
    }
    with patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(schema)):
        # No exception = pass.
        validate_structured_input("test-skill", {"document_id": "abc123"})


def test_validate_rejects_missing_required_field():
    schema = {
        "type": "object",
        "properties": {"document_id": {"type": "string"}},
        "required": ["document_id"],
    }
    with patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(schema)):
        with pytest.raises(StructuredInputInvalidError) as ei:
            validate_structured_input("test-skill", {})
        assert "document_id" in ei.value.errors[0]


def test_validate_rejects_wrong_type():
    schema = {
        "type": "object",
        "properties": {"total": {"type": "number"}},
        "required": ["total"],
    }
    with patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(schema)):
        with pytest.raises(StructuredInputInvalidError):
            validate_structured_input("test-skill", {"total": "not a number"})


def test_validate_raises_not_supported_when_schema_missing():
    with patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(None)):
        with pytest.raises(StructuredInputNotSupportedError):
            validate_structured_input("test-skill", {"anything": 1})


def test_validate_raises_not_found_when_skill_missing():
    with patch("skills.structured_invocation.get_skill", return_value=None):
        with pytest.raises(SkillNotFoundError):
            validate_structured_input("nope", {})


def test_serialize_input_includes_audit_preamble_and_payload():
    msg = serialize_input_as_message({"vendor_name": "Acme", "total": 8500})
    assert "AUDIT-VIEW STANDALONE INVOCATION" in msg
    assert "Acme" in msg
    assert "8500" in msg
    # Payload should be in a json fence so the model parses it cleanly.
    assert "```json" in msg
