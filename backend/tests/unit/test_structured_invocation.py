"""Unit tests for skills.structured_invocation — Audit View standalone runs."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from db.models import SkillConfig
from skills.skill_processor import SkillNotFoundError
from skills.structured_invocation import (
    StandaloneAgentRunError,
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


@pytest.mark.asyncio
async def test_run_collects_tool_results_with_camelcase_keys():
    """Realistic AG-UI event sequence: START → ARGS (streamed) → RESULT.
    Tool call result must end up captured under tool_calls[i].result.
    """
    from skills.structured_invocation import run_structured_invocation

    schema = {
        "type": "object",
        "properties": {"document_id": {"type": "string", "minLength": 1}},
        "required": ["document_id"],
    }

    events = [
        {"type": "TOOL_CALL_START", "toolCallId": "tc-1", "toolCallName": "structured_extraction"},
        {"type": "TOOL_CALL_ARGS", "toolCallId": "tc-1", "delta": '{"document_id"'},
        {"type": "TOOL_CALL_ARGS", "toolCallId": "tc-1", "delta": ':"abc123"}'},
        {"type": "TOOL_CALL_RESULT", "toolCallId": "tc-1", "content": '{"vendor_name":"Acme","total":8500}'},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "Extraction complete."},
    ]

    async def fake_proc(*args, **kwargs):
        for e in events:
            yield e

    with (
        patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(schema)),
        patch("skills.structured_invocation.process_skill_request", side_effect=fake_proc),
    ):
        result = await run_structured_invocation(
            skill_id="test-skill",
            user=None,  # type: ignore[arg-type]
            access=None,  # type: ignore[arg-type]
            payload={"document_id": "abc123"},
            session_id=None,
        )
    assert result["text"] == "Extraction complete."
    assert len(result["tool_calls"]) == 1
    tc = result["tool_calls"][0]
    assert tc["name"] == "structured_extraction"
    assert tc["args"] == '{"document_id":"abc123"}'
    assert tc["result"] == '{"vendor_name":"Acme","total":8500}'


@pytest.mark.asyncio
async def test_run_handles_snake_case_keys_defensively():
    """Some transports / older event versions emit snake_case keys
    (tool_call_id, tool_call_name). The capture loop should still
    match the result back to the right call."""
    from skills.structured_invocation import run_structured_invocation

    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    events = [
        {"type": "TOOL_CALL_START", "tool_call_id": "tc-9", "tool_call_name": "list_documents"},
        {"type": "TOOL_CALL_RESULT", "tool_call_id": "tc-9", "content": '[{"id": "d1"}]'},
    ]

    async def fake_proc(*args, **kwargs):
        for e in events:
            yield e

    with (
        patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(schema)),
        patch("skills.structured_invocation.process_skill_request", side_effect=fake_proc),
    ):
        result = await run_structured_invocation(
            skill_id="test-skill",
            user=None,  # type: ignore[arg-type]
            access=None,  # type: ignore[arg-type]
            payload={"x": "y"},
            session_id=None,
        )
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "list_documents"
    assert result["tool_calls"][0]["result"] == '[{"id": "d1"}]'


@pytest.mark.asyncio
async def test_run_raises_on_run_error_event():
    """RUN_ERROR mid-stream means the agent / session service failed
    (Vertex 404, budget, auth, etc). Without this guard the loop would
    finish and return a 200 with 0 tool calls — the UI then shows the
    misleading "specialist returned no tool calls" message. Propagate
    as StandaloneAgentRunError so the route returns 502.
    """
    from skills.structured_invocation import run_structured_invocation

    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    events = [
        {"type": "TOOL_CALL_START", "toolCallId": "tc-1", "toolCallName": "list_documents"},
        {"type": "RUN_ERROR", "message": "404 NOT_FOUND. The ReasoningEngine does not exist.", "code": "VERTEX_404"},
    ]

    async def fake_proc(*args, **kwargs):
        for e in events:
            yield e

    with (
        patch("skills.structured_invocation.get_skill", return_value=_make_skill_with_schema(schema)),
        patch("skills.structured_invocation.process_skill_request", side_effect=fake_proc),
    ):
        with pytest.raises(StandaloneAgentRunError) as ei:
            await run_structured_invocation(
                skill_id="test-skill",
                user=None,  # type: ignore[arg-type]
                access=None,  # type: ignore[arg-type]
                payload={"x": "y"},
                session_id=None,
            )
    assert "ReasoningEngine" in ei.value.message
    assert ei.value.code == "VERTEX_404"


def test_serialize_input_includes_audit_preamble_and_payload():
    msg = serialize_input_as_message({"vendor_name": "Acme", "total": 8500})
    assert "AUDIT-VIEW STANDALONE INVOCATION" in msg
    assert "Acme" in msg
    assert "8500" in msg
    # Payload should be in a json fence so the model parses it cleanly.
    assert "```json" in msg
