"""Tests for tools/mcp/registry.py and adk/tools.py MCP wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset


class TestGetMcpTools:
    def test_returns_toolset_for_http_server(self):
        from tools.mcp.registry import get_mcp_tools

        config = {"url": "http://localhost:9000/mcp", "transport": "http"}
        with patch("tools.mcp.registry.get_document", return_value=config):
            result = get_mcp_tools(["my-server"])

        assert len(result) == 1
        assert isinstance(result[0], McpToolset)

    def test_returns_sse_toolset_for_sse_transport(self):
        from tools.mcp.registry import _build_toolset

        config = {"url": "http://localhost:9000/sse", "transport": "sse"}
        toolset = _build_toolset("test-server", config)
        assert isinstance(toolset, McpToolset)
        assert isinstance(toolset._connection_params, SseConnectionParams)

    def test_returns_http_toolset_for_http_transport(self):
        from tools.mcp.registry import _build_toolset

        config = {"url": "http://localhost:9000/mcp", "transport": "http"}
        toolset = _build_toolset("test-server", config)
        assert isinstance(toolset, McpToolset)
        assert isinstance(toolset._connection_params, StreamableHTTPConnectionParams)

    def test_defaults_to_http_transport(self):
        from tools.mcp.registry import _build_toolset

        config = {"url": "http://localhost:9000/mcp"}
        toolset = _build_toolset("test-server", config)
        assert isinstance(toolset._connection_params, StreamableHTTPConnectionParams)

    def test_skips_server_not_found_in_firestore(self):
        from tools.mcp.registry import get_mcp_tools

        with patch("tools.mcp.registry.get_document", return_value=None):
            result = get_mcp_tools(["missing-server"])

        assert result == []

    def test_skips_server_missing_url(self):
        from tools.mcp.registry import _build_toolset

        result = _build_toolset("bad-server", {"transport": "http"})
        assert result is None

    def test_skips_server_on_firestore_error(self):
        from tools.mcp.registry import get_mcp_tools

        with patch("tools.mcp.registry.get_document", side_effect=RuntimeError("network")):
            result = get_mcp_tools(["broken-server"])

        assert result == []

    def test_returns_multiple_toolsets(self):
        from tools.mcp.registry import get_mcp_tools

        configs = {
            "server-a": {"url": "http://a.example.com/mcp"},
            "server-b": {"url": "http://b.example.com/mcp"},
        }
        with patch("tools.mcp.registry.get_document", side_effect=lambda _, sid: configs[sid]):
            result = get_mcp_tools(["server-a", "server-b"])

        assert len(result) == 2


class TestResolveMcpTools:
    def test_empty_when_no_mcp_config(self):
        from adk.tools import resolve_mcp_tools

        result = resolve_mcp_tools({})
        assert result == []

    def test_empty_when_mcp_has_no_servers(self):
        from adk.tools import resolve_mcp_tools

        result = resolve_mcp_tools({"mcp": {}})
        assert result == []

    def test_calls_get_mcp_tools_with_server_ids(self):
        from unittest.mock import MagicMock

        from adk.tools import resolve_mcp_tools

        ts1 = MagicMock(aitana_server_id="srv-1")
        ts2 = MagicMock(aitana_server_id="srv-2")
        with patch("tools.mcp.registry.get_mcp_tools", return_value=[ts1, ts2]) as mock:
            result = resolve_mcp_tools({"mcp": {"servers": ["srv-1", "srv-2"]}})

        mock.assert_called_once_with(["srv-1", "srv-2"])
        assert result == [ts1, ts2]

    def test_raises_when_declared_server_silently_skipped(self):
        """The silent-skip path historically masked the Cloud Run multi-container
        misconfig — fail loud at build time instead.
        """
        from unittest.mock import MagicMock

        from adk.tools import resolve_mcp_tools

        # Only one of the two declared servers resolved.
        ts1 = MagicMock(aitana_server_id="srv-1")
        with patch("tools.mcp.registry.get_mcp_tools", return_value=[ts1]):
            with pytest.raises(ValueError, match=r"srv-2.*Firestore mcp_servers"):
                resolve_mcp_tools({"mcp": {"servers": ["srv-1", "srv-2"]}})

    def test_allows_optional_server_to_no_op(self):
        """Servers listed under mcp.optional may be missing without raising."""
        from unittest.mock import MagicMock

        from adk.tools import resolve_mcp_tools

        ts1 = MagicMock(aitana_server_id="srv-1")
        with patch("tools.mcp.registry.get_mcp_tools", return_value=[ts1]):
            result = resolve_mcp_tools({"mcp": {"servers": ["srv-1", "srv-2"], "optional": ["srv-2"]}})
        assert result == [ts1]


class TestResolveToolsErrors:
    def test_raises_on_unknown_tool(self):
        from adk.tools import resolve_tools

        with pytest.raises(ValueError, match="Unknown tool"):
            resolve_tools(["nonexistent_tool"], {})

    def test_model_aware_tools_do_not_raise(self):
        from adk.tools import resolve_tools

        # ai_search and google_search are model-aware — no ValueError
        result = resolve_tools(["ai_search", "google_search"], {})
        assert result == []

    def test_mcp_tool_does_not_raise(self):
        from adk.tools import resolve_tools

        result = resolve_tools(["mcp"], {})
        assert result == []

    def test_code_execution_does_not_raise(self):
        from adk.tools import resolve_tools

        result = resolve_tools(["code_execution"], {})
        assert result == []
