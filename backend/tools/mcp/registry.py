"""MCP toolset registry — loads McpToolset instances from Firestore server configs.

Firestore schema: mcp_servers/{server_id}
  url:       str  — HTTP or SSE endpoint URL
  transport: str  — "http" (default) | "sse"
  headers:   dict — optional HTTP headers (e.g. Authorization)
  name:      str  — human-readable label

Usage from adk/tools.py via resolve_tools when "mcp" is in tool_names:
  configs = skill_tool_config.get("mcp", {}).get("servers", [])
  toolsets = get_mcp_tools(configs)

UI capability declaration (M2B-BACKEND, MCP-APP-INTEGRATIONS):
  Per the MCP Apps spec the *client* should advertise that it can render UI
  resources back from the server. The canonical mechanism is the
  ``ClientSession`` ``capabilities`` arg::

      capabilities = {"extensions": {"io.modelcontextprotocol/ui": {
          "mimeTypes": ["text/html;profile=mcp-app"],
      }}}

  ADK as of v1.24.1 does NOT plumb that arg through ``StreamableHTTPConnectionParams``
  → ``MCPSessionManager._create_client`` → ``streamablehttp_client(...)`` →
  ``ClientSession.initialize()`` (verified via mcp__adk-mcp__search_code on
  2026-04-30). Workaround: declare the capability via a static HTTP header
  (``UI_CAPABILITY_HEADER``) on the connection params. Spec-compliant servers
  should key off it; the live ext-apps map-server emits UI resources
  unconditionally so the demo works either way. See
  ``docs/design/v6.1.0/mcp-app-integrations.md`` Open Questions.

  When ADK adds capability passthrough, swap the header for the canonical
  ``capabilities`` arg and remove ``UI_CAPABILITY_HEADER`` from this file.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from db.firestore import get_document

log = logging.getLogger(__name__)

_MCP_COLLECTION = "mcp_servers"

# Attribute name we stamp on every produced MCPTool so observability callbacks
# (see ``adk/mcp_observability.py``) can recover the originating server_id
# without parsing tool names. Subclassing keeps LLM-visible tool names
# unchanged — the alternative (``tool_name_prefix``) would change them.
SERVER_ID_ATTR = "_aitana_mcp_server_id"

# UI capability declaration — see module docstring for the workaround
# rationale. Lives on the connection params headers dict, merged with any
# server-configured headers (operator-supplied value wins on collision).
UI_CAPABILITY_HEADER = "x-aitana-mcp-ui-supported"
UI_CAPABILITY_MIME_TYPE = "text/html;profile=mcp-app"


class TaggedMcpToolset(McpToolset):
    """McpToolset subclass that tags every produced MCPTool with its server_id.

    Why a subclass and not ``tool_name_prefix``: the prefix would alter the
    function names the LLM sees (``mcp_<server>_<tool>`` instead of just
    ``<tool>``), which would surprise prompts that reference tool names
    explicitly and complicate the workshop demo. Stamping a private
    attribute on each tool keeps the LLM-visible surface unchanged and
    gives observability callbacks a clean way to recover the server_id.
    """

    def __init__(self, *, server_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._aitana_server_id = server_id

    @property
    def aitana_server_id(self) -> str:
        return self._aitana_server_id

    async def get_tools(self, readonly_context: ReadonlyContext | None = None):  # type: ignore[override]
        tools = await super().get_tools(readonly_context=readonly_context)
        for tool in tools:
            try:
                setattr(tool, SERVER_ID_ATTR, self._aitana_server_id)
            except Exception as exc:  # pragma: no cover - defensive
                log.debug("mcp_registry: failed to tag tool %r with server_id: %s", tool, exc)
        return tools


def get_mcp_tools(server_ids: list[str]) -> list[McpToolset]:
    """Return McpToolset instances for the given server IDs.

    Reads each server's config from Firestore `mcp_servers/{server_id}`.
    Servers not found in Firestore are logged and skipped.

    Args:
        server_ids: List of Firestore document IDs under mcp_servers/.

    Returns:
        List of McpToolset instances ready to add to an agent's tools list.
    """
    toolsets: list[McpToolset] = []
    for server_id in server_ids:
        try:
            config = get_document(_MCP_COLLECTION, server_id)
        except Exception as exc:
            log.warning("mcp_registry: failed to load server config %r: %s", server_id, exc)
            continue

        if config is None:
            log.warning("mcp_registry: server %r not found in Firestore; skipping", server_id)
            continue

        toolset = _build_toolset(server_id, config)
        if toolset is not None:
            toolsets.append(toolset)

    return toolsets


def _merge_ui_capability_header(headers: dict) -> dict:
    """Return headers dict with the UI capability header set, unless the
    operator already supplied their own value (which wins).
    """
    merged = dict(headers) if headers else {}
    if UI_CAPABILITY_HEADER not in merged:
        merged[UI_CAPABILITY_HEADER] = UI_CAPABILITY_MIME_TYPE
    return merged


def _build_toolset(server_id: str, config: dict) -> McpToolset | None:
    """Build a McpToolset from a Firestore server config dict.

    Always declares UI extension capability via ``UI_CAPABILITY_HEADER`` so
    spec-compliant servers know they can return UI resources. See module
    docstring for why this is the workaround path rather than the canonical
    ``ClientSession.capabilities`` arg.
    """
    url = config.get("url")
    if not url:
        log.warning("mcp_registry: server %r has no url field; skipping", server_id)
        return None

    transport = config.get("transport", "http").lower()
    server_headers = config.get("headers") or {}
    headers = _merge_ui_capability_header(server_headers)

    if transport == "sse":
        connection = SseConnectionParams(url=url, headers=headers)
    else:
        connection = StreamableHTTPConnectionParams(url=url, headers=headers)

    return TaggedMcpToolset(server_id=server_id, connection_params=connection)
