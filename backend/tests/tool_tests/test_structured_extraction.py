"""Tests for tools/structured_extraction.py."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_ctx(state: dict | None = None):
    ctx = MagicMock()
    ctx.state = state or {}
    ctx.save_artifact = AsyncMock()
    return ctx


class TestStructuredExtractionCallbackSkips:
    @pytest.mark.asyncio
    async def test_no_op_when_no_schema(self):
        from tools.structured_extraction import structured_extraction_callback

        ctx = _make_ctx({"temp:document_blocks": "[]"})
        result = await structured_extraction_callback(ctx)
        assert result is None
        assert "temp:extraction_result" not in ctx.state

    @pytest.mark.asyncio
    async def test_no_op_when_no_blocks(self):
        from tools.structured_extraction import structured_extraction_callback

        ctx = _make_ctx({"app:extraction_schema": {"type": "object"}})
        result = await structured_extraction_callback(ctx)
        assert result is None
        assert "temp:extraction_result" not in ctx.state


class TestStructuredExtractionCallbackRuns:
    @pytest.mark.asyncio
    async def test_stores_result_in_state(self):
        from tools.structured_extraction import structured_extraction_callback

        extracted = {"invoice_number": "INV-001", "total": "100"}
        ctx = _make_ctx(
            {
                "app:extraction_schema": {"type": "object"},
                "temp:document_blocks": '[{"type": "paragraph", "text": "Invoice INV-001"}]',
                "temp:document_id": "doc-abc",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps(extracted))):
            await structured_extraction_callback(ctx)

        assert "temp:extraction_result" in ctx.state
        parsed = json.loads(ctx.state["temp:extraction_result"])
        assert parsed["invoice_number"] == "INV-001"

    @pytest.mark.asyncio
    async def test_accepts_schema_as_string(self):
        from tools.structured_extraction import structured_extraction_callback

        schema_str = json.dumps({"type": "object", "properties": {"name": {"type": "string"}}})
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema_str,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-x",
            }
        )
        extracted = {"name": "Test"}

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps(extracted))):
            await structured_extraction_callback(ctx)

        assert json.loads(ctx.state["temp:extraction_result"])["name"] == "Test"

    @pytest.mark.asyncio
    async def test_stores_error_on_extraction_failure(self):
        from tools.structured_extraction import structured_extraction_callback

        ctx = _make_ctx(
            {
                "app:extraction_schema": {"type": "object"},
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-fail",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(side_effect=RuntimeError("boom"))):
            await structured_extraction_callback(ctx)

        result = json.loads(ctx.state["temp:extraction_result"])
        assert "error" in result
        assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_saves_artifact_for_large_result(self):
        from tools.structured_extraction import _LARGE_OUTPUT_THRESHOLD, structured_extraction_callback

        large_json = json.dumps({"data": "x" * (_LARGE_OUTPUT_THRESHOLD + 1)})
        ctx = _make_ctx(
            {
                "app:extraction_schema": {"type": "object"},
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-large",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=large_json)):
            with patch("tools.structured_extraction.genai_types") as mock_types:
                mock_types.Part.from_text.return_value = MagicMock()
                await structured_extraction_callback(ctx)

        ctx.save_artifact.assert_awaited_once()
        meta = json.loads(ctx.state["temp:extraction_result"])
        assert meta.get("truncated") is True
        assert "artifact_id" in meta


class TestSchemaEnforcedReturn:
    """SCHEMA-ENFORCE M3: callback returns types.Content with validated JSON.

    ADK's after_agent_callback contract: a non-None return is appended as
    an additional agent response. We use this to make the validated
    extraction the final TEXT_MESSAGE in the AG-UI stream.
    """

    @pytest.mark.asyncio
    async def test_valid_extraction_returns_content_with_json(self):
        from tools.structured_extraction import structured_extraction_callback

        schema = {
            "type": "object",
            "properties": {"vendor": {"type": "string"}, "total": {"type": "number"}},
            "required": ["vendor", "total"],
            "additionalProperties": False,
        }
        extracted = {"vendor": "Acme GmbH", "total": 9000}
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-acme",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps(extracted))):
            result = await structured_extraction_callback(ctx)

        # Returned types.Content carries the validated JSON for ADK to append
        assert result is not None
        # The validated JSON also lands in state for sub-agents that pull from state
        assert json.loads(ctx.state["temp:extraction_result"]) == extracted
        # No validation errors when output matches schema
        assert "temp:extraction_validation_errors" not in ctx.state

    @pytest.mark.asyncio
    async def test_invalid_output_records_violations_but_still_returns_content(self):
        """Graceful degradation: surface broken output + log errors, don't crash."""
        from tools.structured_extraction import structured_extraction_callback

        schema = {
            "type": "object",
            "properties": {"vendor": {"type": "string"}, "total": {"type": "number"}},
            "required": ["vendor", "total"],
        }
        # Missing required `total`, vendor wrong type
        broken = {"vendor": 42}
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-broken",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps(broken))):
            result = await structured_extraction_callback(ctx)

        # Still returns content (graceful degradation) so the audit view shows
        # the broken output instead of "specialist returned no tool calls".
        assert result is not None
        errors = ctx.state.get("temp:extraction_validation_errors", [])
        assert errors, "validation errors should be recorded"
        assert any("total" in err for err in errors), f"expected 'total' violation in {errors!r}"

    @pytest.mark.asyncio
    async def test_extraction_failure_returns_none(self):
        """When the Gemini call itself errors, no Content is returned —
        the error envelope in state is the only output."""
        from tools.structured_extraction import structured_extraction_callback

        ctx = _make_ctx(
            {
                "app:extraction_schema": {"type": "object"},
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-fail",
            }
        )

        with patch(
            "tools.structured_extraction._run_extraction", new=AsyncMock(side_effect=RuntimeError("Vertex auth"))
        ):
            result = await structured_extraction_callback(ctx)

        assert result is None
        assert "error" in json.loads(ctx.state["temp:extraction_result"])

    @pytest.mark.asyncio
    async def test_clears_stale_validation_errors_on_success(self):
        """Next-turn-with-valid-output must wipe prior errors."""
        from tools.structured_extraction import structured_extraction_callback

        schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-1",
                "temp:extraction_validation_errors": ["leftover from prior run"],
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps({"x": "ok"}))):
            await structured_extraction_callback(ctx)

        assert "temp:extraction_validation_errors" not in ctx.state


class TestA2UIPreviewCardEmission:
    """The callback must emit an A2UI Card alongside the JSON text Part so
    the chat bubble renders a Card instead of a raw JSON code block.

    The emission rides on a synthesised ``send_a2ui_json_to_client``
    function_call + function_response Part pair on the returned Content.
    AG-UI's event translator turns those into TOOL_CALL_START /
    TOOL_CALL_END / TOOL_CALL_RESULT events the frontend already routes
    via MessageBubble.parseA2UIResult.

    These tests are the regression guard for the "JSON blob in chat"
    anti-pattern called out in the GE / A2UI integration guide.
    """

    @pytest.mark.asyncio
    async def test_successful_extraction_appends_a2ui_function_call_and_response(self):
        from tools.structured_extraction import structured_extraction_callback

        schema = {
            "type": "object",
            "title": "AP Invoice",
            "properties": {"vendor": {"type": "string"}, "total": {"type": "number"}},
        }
        extracted = {"vendor": "Acme GmbH", "total": 9000}
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-acme",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps(extracted))):
            result = await structured_extraction_callback(ctx)

        assert result is not None
        parts = result.parts
        # Three Parts: text (for downstream agents) + function_call + function_response.
        function_calls = [p.function_call for p in parts if getattr(p, "function_call", None) is not None]
        function_responses = [p.function_response for p in parts if getattr(p, "function_response", None) is not None]
        assert len(function_calls) == 1, "expected exactly one synthesised function_call"
        assert len(function_responses) == 1, "expected exactly one synthesised function_response"
        # Tool name is the canonical A2UI emit tool — that's what the
        # frontend's MessageBubble filters on.
        assert function_calls[0].name == "send_a2ui_json_to_client"
        assert function_responses[0].name == "send_a2ui_json_to_client"
        # IDs must match so AG-UI pairs the call with the result.
        assert function_calls[0].id == function_responses[0].id

    @pytest.mark.asyncio
    async def test_a2ui_response_carries_mime_tag_and_surface(self):
        """The function_response.response dict is what the frontend reads
        via parseA2UIResult. It must carry the v0.9 message array plus
        the MIME tag + surface routing the SDK envelope uses."""
        from tools.structured_extraction import structured_extraction_callback

        schema = {"type": "object", "title": "X", "properties": {"a": {"type": "string"}}}
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-mime",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps({"a": "v"}))):
            result = await structured_extraction_callback(ctx)

        responses = [p.function_response for p in result.parts if getattr(p, "function_response", None) is not None]
        envelope = responses[0].response
        assert envelope["mime_type"] == "application/json+a2ui"
        assert envelope["surface_id"] == "chat"
        assert envelope["update_mode"] == "replace"
        # The v0.9 array must contain at least createSurface + updateComponents.
        messages = envelope["validated_a2ui_json"]
        assert any("createSurface" in m for m in messages)
        assert any("updateComponents" in m for m in messages)

    @pytest.mark.asyncio
    async def test_text_part_for_json_is_still_emitted_for_downstream_agents(self):
        """Downstream agents (ap-validator transfer, structured_invocation)
        JSON.parse the text Part. The A2UI emission MUST be additive — it
        must never remove the text Part. Frontend handles the visual
        duplicate via isLikelyJsonOnly()."""
        from tools.structured_extraction import structured_extraction_callback

        schema = {"type": "object", "properties": {"vendor": {"type": "string"}}}
        ctx = _make_ctx(
            {
                "app:extraction_schema": schema,
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-text-kept",
            }
        )

        with patch(
            "tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps({"vendor": "Acme"}))
        ):
            result = await structured_extraction_callback(ctx)

        text_parts = [p.text for p in result.parts if getattr(p, "text", None)]
        assert len(text_parts) == 1
        assert json.loads(text_parts[0])["vendor"] == "Acme"

    @pytest.mark.asyncio
    async def test_no_a2ui_emission_when_schema_is_a_string(self):
        """The card builder needs a dict-shaped schema. When `app:extraction_schema`
        was set as a JSON string (older callers), the text JSON Part still goes
        out — only the optional A2UI emission is skipped. No crash."""
        from tools.structured_extraction import structured_extraction_callback

        ctx = _make_ctx(
            {
                "app:extraction_schema": '{"type":"object"}',  # string, not dict
                "temp:document_blocks": "[]",
                "temp:document_id": "doc-str-schema",
            }
        )

        with patch("tools.structured_extraction._run_extraction", new=AsyncMock(return_value=json.dumps({"a": 1}))):
            result = await structured_extraction_callback(ctx)

        assert result is not None
        # Text Part survives.
        text_parts = [p.text for p in result.parts if getattr(p, "text", None)]
        assert len(text_parts) == 1
        # No A2UI emission when schema isn't a dict.
        function_responses = [
            p.function_response for p in result.parts if getattr(p, "function_response", None) is not None
        ]
        assert function_responses == []


class TestRunExtraction:
    @pytest.mark.asyncio
    async def test_returns_json_string(self):
        from tools.structured_extraction import _run_extraction

        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        blocks_json = '[{"type": "paragraph", "text": "Alice signed the contract."}]'
        expected = {"name": "Alice"}

        mock_response = MagicMock()
        mock_response.text = json.dumps(expected)

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("tools.structured_extraction.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = await _run_extraction(blocks_json, schema)

        parsed = json.loads(result)
        assert parsed["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_raises_on_empty_response(self):
        from tools.structured_extraction import _run_extraction

        mock_response = MagicMock()
        mock_response.text = ""

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("tools.structured_extraction.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            with pytest.raises(ValueError, match="empty"):
                await _run_extraction("[]", {"type": "object"})

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json_response(self):
        from tools.structured_extraction import _run_extraction

        mock_response = MagicMock()
        mock_response.text = "not json at all"

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("tools.structured_extraction.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            with pytest.raises(json.JSONDecodeError):
                await _run_extraction("[]", {"type": "object"})
