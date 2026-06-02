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


# Visual rendering of the extracted JSON as a Card is the frontend's
# responsibility — see frontend/src/components/chat/JsonCardBuilder.ts.
# The backend callback's job ends at emitting the schema-validated JSON
# as a text Part; the frontend turns that into a styled Card when the
# bubble's text is JSON-only. A previous attempt to emit A2UI from the
# callback by synthesising function_call / function_response Parts was
# abandoned 2026-06-02 because the genai SDK strips function_response
# Parts from role="model" Content.


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
