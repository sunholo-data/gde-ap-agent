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
