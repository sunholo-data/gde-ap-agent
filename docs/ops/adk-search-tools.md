# ADK Search Tool Compatibility

Reference for how to wire search tools in v6. Discovered during CHAT-POLISH sprint (2026-04-24) via ADK MCP server + integration testing against real Vertex AI.

## The Core Constraint

Gemini's API rejects mixed tool types in a single request with:

```
400 INVALID_ARGUMENT: Multiple tools are supported only when they are all search tools.
```

This fires whenever a Gemini agent has both a **grounding built-in** (`google_search`, `url_context`, `VertexAiSearchTool`) and a **FunctionTool** in its tool list. The error name is misleading — the issue is not about having multiple search tools, it's about mixing grounding built-ins with FunctionTools.

ADK tracks this as an open bug: **TODO(b/448114567)**. Once Google fixes it at the API level, the sub-agent workaround can be removed and tools can be placed directly on the root agent.

## The Sub-Agent Pattern

All search in v6 goes through a dedicated search sub-agent, wrapped as an `AgentTool`. The root agent only ever has FunctionTools; grounding built-ins live inside the sub-agent's isolated request. ADK calls its own implementation of this `GoogleSearchAgentTool`.

```
Root agent (FunctionTools only)
  ├── retrieve_artifact       ← FunctionTool, fine on any agent
  ├── make_a2ui_toolset()     ← FunctionTool, fine on any agent
  ├── GoogleSearchAgentTool   ← AgentTool wrapping web_search_agent
  │     └── web_search_agent (gemini-2.5-flash)
  │           ├── google_search   ← built-in, isolated
  │           └── url_context     ← built-in, isolated
  └── AgentTool               ← wrapping enterprise_search_agent
        └── enterprise_search_agent (gemini-2.5-flash)
              └── VertexAiSearchTool  ← built-in, isolated
```

## google_search vs VertexAiSearchTool — Two Different API Types

`google_search` and `VertexAiSearchTool` are incompatible even with each other on the same agent. They emit different `types.Tool` shapes:

| Tool | API shape | 
|------|-----------|
| `google_search` | `types.Tool(google_search=types.GoogleSearch())` |
| `url_context` | `types.Tool(url_context=types.UrlContext())` |
| `VertexAiSearchTool` | `types.Tool(retrieval=types.Retrieval(vertex_ai_search=...))` |

Combining `google_search` + `VertexAiSearchTool` on the same sub-agent also causes the 400. So web and enterprise search each need their own agent.

## Our Implementation

### `tools/search_agent.py`

```python
create_web_search_agent()        # → LlmAgent("web_search_agent", tools=[google_search, url_context])
create_enterprise_search_agent(datastore_id)  # → LlmAgent("enterprise_search_agent", tools=[VertexAiSearchTool])
create_search_agent(datastore_id=None)  # convenience wrapper → one of the above
```

### `adk/agent.py` — `_resolve_search_tools()`

```
google_search in skill tools → GoogleSearchAgentTool(create_web_search_agent())
ai_search in skill tools     → AgentTool(create_enterprise_search_agent(ds_id), propagate_grounding_metadata=True)
both                         → two AgentTools returned, both added to root agent
ai_search but no datastore_id → warning logged, skipped
```

## `propagate_grounding_metadata=True`

Grounding metadata contains source URLs for citation rendering. Without `propagate_grounding_metadata=True`, citation data produced by the search sub-agent is silently dropped and never reaches the parent session.

ADK's `GoogleSearchAgentTool` sets this flag automatically. For enterprise search we pass it explicitly:

```python
AgentTool(create_enterprise_search_agent(datastore_id), propagate_grounding_metadata=True)
```

## `bypass_multi_tools_limit` Flag

Both `GoogleSearchTool` (via `GoogleSearchTool(bypass_multi_tools_limit=True)`) and `VertexAiSearchTool(bypass_multi_tools_limit=True)` accept this flag. It suppresses a client-side validation check. We **do not use it** because:

1. It bypasses validation but does not fix the underlying API restriction — behaviour is undefined.
2. `google_search` and `VertexAiSearchTool` still cannot coexist on the same agent even with the flag.
3. The sub-agent pattern is the correct documented workaround.

## Vertex AI Search Datastore

- **GCP project:** `aitana-ai-search` (separate project dedicated to search infra)
- **Datastore resource ID:** `projects/aitana-ai-search/locations/eu/collections/default_collection/dataStores/aitana3`
- **Env var:** `VERTEX_AI_SEARCH_DATASTORE_ID` (set in `backend/.env`, excluded from git)
- **List datastores:** `gcloud alpha discovery-engine data-stores list --project=aitana-ai-search --location=eu`

## Integration Tests

```bash
# All 6 tests (requires ADC + VERTEX_AI_SEARCH_DATASTORE_ID):
cd backend
set -a && source .env && set +a
uv run pytest tests/integration/test_search_agent.py -v -m integration

# Web-only (no env var needed):
uv run pytest tests/integration/test_search_agent.py -v -m integration -k "not vertex_ai_search"
```

## When ADK Fixes This

When `b/448114567` is resolved, the fix will likely allow grounding built-ins and FunctionTools to coexist on the same agent request. At that point:

1. Remove the `_resolve_search_tools` sub-agent indirection in `adk/agent.py`
2. Add `google_search`, `url_context`, `VertexAiSearchTool` directly to the root agent tool list
3. Delete `create_web_search_agent`, `create_enterprise_search_agent` from `tools/search_agent.py`
4. Check ADK release notes for the `GoogleSearchAgentTool` deprecation notice (they said they'll remove it)
