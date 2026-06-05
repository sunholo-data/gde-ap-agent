"""ADK FunctionTool registry — maps skill-config tool names to callables.

Model-aware routing:
  - Gemini agents receive ADK built-in tools (VertexAiSearchTool, GoogleSearchTool,
    UrlContextTool) added directly, not via this registry.
  - Claude/OpenAI agents receive AgentTool wrappers created in agent.py.
  - Document tools (list_documents, get_document_content) are the same for all models.
  - Stubs remain for tools not yet ported (code_execution, user_history).

Tools ported in sprint TOOLS-PORTING:
  - list_documents / get_document_content (M1)
  - ai_search / google_search / url_processing (M2, model-aware in agent.py)
  - structured_extraction (M3, registered as after_agent callback, not here)
  - code_execution (M4, model-aware in agent.py)
  - mcp (M5, loaded via mcp/registry.py)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from google.adk.tools import FunctionTool, ToolContext

from db.firestore import query_documents
from tools.ap_pipeline_emit import EMIT_TOOLS
from tools.documents.context import build_document_context
from tools.url_processing import url_processing
from tools.workshop_docs import search_workshop_docs

logger = logging.getLogger(__name__)

_PARSED_DOCS_COLLECTION = "parsed_documents"


# --- Document tools ---


async def list_documents(
    skill_id: str | None = None,
    limit: int = 20,
    tool_context: ToolContext = None,
) -> str:
    """List parsed documents available in the workspace.

    Args:
        skill_id: Optional skill ID to filter documents by. Omit to list all your documents.
        limit: Maximum number of documents to return (default 20, max 50).

    Returns:
        A formatted list of document names, IDs, and status.
    """
    user_id = None
    if tool_context is not None:
        user_id = tool_context.state.get("user:id") or tool_context.state.get("user_id")

    filters: list[tuple[str, str, object]] = []
    if user_id:
        filters.append(("userId", "==", user_id))
    if skill_id:
        filters.append(("skillId", "==", skill_id))
    filters.append(("status", "==", "parsed"))

    effective_limit = min(int(limit), 50)

    try:
        docs = await asyncio.to_thread(
            query_documents,
            collection=_PARSED_DOCS_COLLECTION,
            filters=filters,
            order_by="createdAt",
            order_direction="DESCENDING",
            limit=effective_limit,
        )
    except Exception as exc:
        # Structured failure surfacing: bland "Could not retrieve documents"
        # gets paraphrased away by the LLM into a misleading "no documents
        # found" response. The [TOOL_ERROR] prefix is a convention the
        # specialist SKILL.md files relay verbatim so the user sees the
        # actual root cause in the chat (eg. missing Firestore index,
        # permission denied) rather than a hung "thinking…" indicator.
        logger.warning(
            "list_documents.failed user_id=%s skill_id=%s exc_type=%s msg=%s",
            user_id or "anonymous",
            skill_id or "all",
            type(exc).__name__,
            exc,
        )
        return (
            f"[TOOL_ERROR] list_documents failed ({type(exc).__name__}): {exc}. "
            "Report this error to the user verbatim — do NOT claim there are no "
            "documents available."
        )

    if not docs:
        return "No documents found in the workspace."

    lines = [f"Found {len(docs)} document(s):\n"]
    for doc in docs:
        doc_id = doc.get("__id", "?")
        filename = doc.get("originalFilename", "Unknown")
        status = doc.get("status", "unknown")
        fmt = doc.get("sourceFormat", "")
        summary = doc.get("summary") or {}
        blocks_count = summary.get("totalBlocks", 0)
        lines.append(f"- {filename} (id: {doc_id}, format: {fmt}, blocks: {blocks_count}, status: {status})")

    return "\n".join(lines)


async def get_document_content(
    doc_id: str,
    section: str | None = None,
    mode: str = "markdown",
    tool_context: ToolContext = None,
) -> str:
    """Get content of a parsed document.

    Args:
        doc_id: The document ID from list_documents.
        section: Optional section heading to extract (case-insensitive substring). Omit for full document.
        mode: Output format — "markdown" for reading/chat (default), "blocks" for extraction tasks
              where table structure and tracked changes must be preserved exactly.

    Returns:
        Document content as markdown, or JSON blocks string when mode="blocks".
    """
    try:
        content, blocks = await asyncio.to_thread(build_document_context, doc_id, mode, section)
    except KeyError:
        return f"Document '{doc_id}' not found. Use list_documents to see available documents."
    except Exception as exc:
        logger.warning(
            "get_document_content.failed doc_id=%s mode=%s exc_type=%s msg=%s",
            doc_id,
            mode,
            type(exc).__name__,
            exc,
        )
        return (
            f"[TOOL_ERROR] get_document_content failed for doc {doc_id!r} "
            f"({type(exc).__name__}): {exc}. Report this error to the user "
            "verbatim — do NOT fabricate document content."
        )

    if mode == "blocks" and blocks is not None and tool_context is not None:
        # Populate session state so structured_extraction_callback can consume blocks
        tool_context.state["temp:document_blocks"] = json.dumps(blocks, ensure_ascii=False)
        tool_context.state["temp:document_id"] = doc_id

    return content


# --- Registry ---
# tool name → factory function(config dict) → FunctionTool
# Model-aware tools (ai_search, google_search, code_execution) are resolved
# directly in agent.py's create_agent() based on the skill's model.
# MCP tools are loaded via tools/mcp/registry.py and returned as McpToolset.

TOOL_REGISTRY: dict[str, Callable[[dict], FunctionTool]] = {
    "list_documents": lambda _config: FunctionTool(list_documents),
    "get_document_content": lambda _config: FunctionTool(get_document_content),
    "url_processing": lambda _config: FunctionTool(url_processing),
    "search_workshop_docs": lambda _config: FunctionTool(search_workshop_docs),
    # Function-as-schema emit tools for the AP pipeline specialists.
    # Each specialist calls its emit_* tool exactly once at end of turn;
    # the typed parameters ARE the schema (Gemini's function-calling
    # enforces them), so we get schema-validated output in ONE LLM call
    # instead of the two-pass response_schema callback pattern.
    # See backend/tools/ap_pipeline_emit.py for the full rationale.
    # Default-arg binding (``tool=tool``) captures the tool per iteration
    # — without it ruff B023 flags the late-binding loop-variable trap.
    **{name: lambda _config, tool=tool: tool for name, tool in EMIT_TOOLS.items()},
}

# Tools handled entirely outside this registry (no ValueError for these)
_MODEL_AWARE = {"ai_search", "google_search", "code_execution"}
# structured_extraction runs as an after_agent callback in agent.py, not as a FunctionTool
_SKIP = {"structured_extraction"}
_MCP_TOOL = "mcp"


def resolve_tools(tool_names: list[str], tool_configs: dict[str, dict]) -> list[FunctionTool]:
    """Resolve a list of tool names to FunctionTool instances.

    Model-aware tools (ai_search, google_search, code_execution) are wired
    separately in agent.py after model detection.
    MCP tools are loaded via tools/mcp/registry.get_mcp_tools() and appended.

    Args:
        tool_names: Tool names from SkillConfig.skill_metadata.tools.
        tool_configs: Per-tool config dict keyed by tool name.

    Returns:
        List of FunctionTool instances ready to pass into an ADK LlmAgent.

    Raises:
        ValueError: If a tool name is not model-aware, not "mcp", and not in
            TOOL_REGISTRY — prevents silent misconfiguration.
    """
    resolved: list[FunctionTool] = []
    for name in tool_names:
        if name in _MODEL_AWARE or name in _SKIP or name == _MCP_TOOL:
            continue
        factory = TOOL_REGISTRY.get(name)
        if factory is None:
            raise ValueError(
                f"Unknown tool {name!r} — not in TOOL_REGISTRY and not model-aware. "
                "Check the skill config or add the tool to TOOL_REGISTRY."
            )
        config = tool_configs.get(name, {})
        resolved.append(factory(config))
    return resolved


def resolve_mcp_tools(tool_configs: dict[str, dict]) -> list:
    """Return McpToolset instances for any MCP servers listed in tool_configs.

    Called from agent.py when "mcp" appears in the skill's tool list.

    Fails loud when a declared server didn't resolve (missing Firestore
    doc, missing URL field, etc.) instead of silently skipping. The
    silent-skip path historically masked a Cloud Run multi-container
    misconfig where the public hostname routed /mcp/* to the wrong
    container; the validator agent booted with an incomplete toolset,
    SKILL.md told the LLM to call missing tools, and ADK raised at
    run time deep in the AG-UI stream. The build-time assertion turns
    that runtime explosion into a deploy-time error with a useful diff.

    Args:
        tool_configs: Per-tool config dict; reads tool_configs["mcp"]["servers"].
            Optional: ``tool_configs["mcp"]["optional"]`` is a list of
            server ids allowed to no-op (e.g. an experimental side-channel
            server that may or may not exist in this environment).

    Returns:
        List of McpToolset instances (empty if no mcp config).

    Raises:
        ValueError: If a declared server (not in ``optional``) didn't
            resolve to a toolset.
    """
    mcp_cfg = tool_configs.get("mcp") or {}
    server_ids: list[str] = mcp_cfg.get("servers", [])
    if not server_ids:
        return []
    optional: set[str] = set(mcp_cfg.get("optional") or [])

    from tools.mcp.registry import get_mcp_tools

    toolsets = get_mcp_tools(server_ids)
    # TaggedMcpToolset exposes the server_id via aitana_server_id; fall back
    # to a duck-typed attribute lookup for plain McpToolset injected in tests.
    resolved_ids = {getattr(ts, "aitana_server_id", None) or getattr(ts, "server_id", None) for ts in toolsets}
    missing_required = [sid for sid in server_ids if sid not in resolved_ids and sid not in optional]
    if missing_required:
        raise ValueError(
            f"MCP server(s) declared in tool_configs.mcp.servers did not resolve: "
            f"{missing_required!r}. Check Firestore mcp_servers/<id> docs exist and "
            "have a 'url' field. Mark a server as 'optional' under "
            "tool_configs.mcp.optional to allow silent skip."
        )
    return toolsets
