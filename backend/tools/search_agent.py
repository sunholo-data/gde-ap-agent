"""Search sub-agent — wraps Gemini native search tools for all skill agents.

All skill agents (Gemini, Claude, OpenAI) use this sub-agent via AgentTool.
The sub-agent runs on Gemini 2.5 Flash internally with native grounding tools.
This keeps the root agent FunctionTool-compatible — Gemini's built-in grounding
tools cannot coexist with FunctionTools on the same agent request.

Tool selection:
  - No datastore_id  → google_search + url_context (open web)
  - With datastore_id → VertexAiSearchTool only (enterprise corpus)

google_search and VertexAiSearchTool use different API-level tool types and
cannot be combined on the same agent request (400 INVALID_ARGUMENT). Skills
that need both web and enterprise search should request both `google_search`
and `ai_search` in their tool list — _resolve_search_tools creates two
separate AgentTool instances in that case.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import VertexAiSearchTool, google_search, url_context

_WEB_INSTRUCTION = (
    "You are a web search assistant. Use the available tools to find relevant "
    "information from the web and return a comprehensive, well-structured answer. "
    "Cite sources where possible."
)

_ENTERPRISE_INSTRUCTION = (
    "You are a knowledge base search assistant. Use the available tools to find "
    "relevant information from the enterprise knowledge base and return a "
    "comprehensive, well-structured answer. Cite sources where possible."
)


def create_web_search_agent() -> LlmAgent:
    """Gemini agent with google_search + url_context for open-web queries."""
    return LlmAgent(
        name="web_search_agent",
        model="gemini-2.5-flash",
        description="Searches the web and fetches URL content. Use for web search and URL lookup.",
        instruction=_WEB_INSTRUCTION,
        tools=[google_search, url_context],
    )


def create_enterprise_search_agent(datastore_id: str) -> LlmAgent:
    """Gemini agent with VertexAiSearchTool for enterprise corpus queries.

    Args:
        datastore_id: Full Vertex AI Search resource ID:
            projects/{project}/locations/{location}/collections/{collection}/dataStores/{id}
    """
    return LlmAgent(
        name="enterprise_search_agent",
        model="gemini-2.5-flash",
        description="Searches the enterprise knowledge base. Use for document and corpus search.",
        instruction=_ENTERPRISE_INSTRUCTION,
        tools=[VertexAiSearchTool(data_store_id=datastore_id)],
    )


def create_search_agent(datastore_id: str | None = None) -> LlmAgent:
    """Create a search agent — web or enterprise depending on datastore_id.

    Convenience wrapper used when only one search type is needed. For skills
    requesting both google_search and ai_search, use _resolve_search_tools in
    adk/agent.py which returns two separate AgentTool instances.

    Args:
        datastore_id: When provided, returns an enterprise search agent
            (VertexAiSearchTool only). When None, returns a web search agent
            (google_search + url_context).
    """
    if datastore_id:
        return create_enterprise_search_agent(datastore_id)
    return create_web_search_agent()
