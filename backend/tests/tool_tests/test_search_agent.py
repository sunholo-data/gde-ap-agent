"""Tests for tools/search_agent.py."""

from __future__ import annotations

import os
from unittest.mock import patch

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool, VertexAiSearchTool, google_search, url_context


class TestCreateWebSearchAgent:
    def test_returns_llm_agent(self):
        from tools.search_agent import create_web_search_agent

        assert isinstance(create_web_search_agent(), LlmAgent)

    def test_name(self):
        from tools.search_agent import create_web_search_agent

        assert create_web_search_agent().name == "web_search_agent"

    def test_has_two_tools(self):
        from tools.search_agent import create_web_search_agent

        assert len(create_web_search_agent().tools) == 2

    def test_includes_google_search_and_url_context(self):
        from tools.search_agent import create_web_search_agent

        tools = create_web_search_agent().tools
        assert google_search in tools
        assert url_context in tools

    def test_no_vertex_search_tool(self):
        from tools.search_agent import create_web_search_agent

        assert not any(isinstance(t, VertexAiSearchTool) for t in create_web_search_agent().tools)


class TestExpandDatastoreId:
    """Bare-id → full resource name expansion.

    Vertex AI Search rejects bare ids with:
      400 INVALID_ARGUMENT ... Invalid Vertex AI datastore resource name.

    SKILL.md authors write a short token (eg. "ds-ap-vendors"); the
    backend expands it at agent-build time using GOOGLE_CLOUD_PROJECT
    + DATASTORE_LOCATION env vars set in cloudbuild.yaml.
    """

    def test_passes_full_resource_name_unchanged(self):
        from tools.search_agent import _expand_datastore_id

        full = "projects/p/locations/eu/collections/default_collection/dataStores/x"
        assert _expand_datastore_id(full) == full

    def test_expands_bare_id_with_project_and_location(self):
        from tools.search_agent import _expand_datastore_id

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "proj-1", "DATASTORE_LOCATION": "eu"}):
            result = _expand_datastore_id("ds-ap-vendors")
        assert result == ("projects/proj-1/locations/eu/collections/default_collection/dataStores/ds-ap-vendors")

    def test_falls_back_to_eu_when_datastore_location_unset(self):
        from tools.search_agent import _expand_datastore_id

        env = {"GOOGLE_CLOUD_PROJECT": "proj-1"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("DATASTORE_LOCATION", None)
            result = _expand_datastore_id("x")
        assert result.startswith("projects/proj-1/locations/eu/")

    def test_returns_bare_id_when_no_project_env(self):
        """Without a project we let Vertex emit its own actionable error
        rather than synthesising a bogus resource name silently."""
        from tools.search_agent import _expand_datastore_id

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            os.environ.pop("GCP_PROJECT_ID", None)
            assert _expand_datastore_id("x") == "x"

    def test_accepts_gcp_project_id_alias(self):
        from tools.search_agent import _expand_datastore_id

        with patch.dict(os.environ, {"GCP_PROJECT_ID": "alt-proj", "DATASTORE_LOCATION": "us"}, clear=False):
            os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
            assert "alt-proj" in _expand_datastore_id("x")


class TestCreateEnterpriseSearchAgent:
    """Enterprise agent uses VertexAiSearchTool exclusively.

    google_search and VertexAiSearchTool use incompatible API-level tool types
    (400 INVALID_ARGUMENT if combined). Each gets its own named sub-agent.
    """

    def test_returns_llm_agent(self):
        from tools.search_agent import create_enterprise_search_agent

        assert isinstance(create_enterprise_search_agent("my-ds"), LlmAgent)

    def test_name(self):
        from tools.search_agent import create_enterprise_search_agent

        assert create_enterprise_search_agent("my-ds").name == "enterprise_search_agent"

    def test_has_one_tool(self):
        from tools.search_agent import create_enterprise_search_agent

        assert len(create_enterprise_search_agent("my-ds").tools) == 1

    def test_includes_vertex_search_with_correct_datastore(self):
        """When passed a full resource name, the factory uses it verbatim
        (no expansion). Bare ids go through _expand_datastore_id —
        covered separately in TestExpandDatastoreId."""
        from tools.search_agent import create_enterprise_search_agent

        full = "projects/p/locations/eu/collections/default_collection/dataStores/my-ds"
        agent = create_enterprise_search_agent(full)
        vertex_tools = [t for t in agent.tools if isinstance(t, VertexAiSearchTool)]
        assert len(vertex_tools) == 1
        assert vertex_tools[0].data_store_id == full

    def test_no_google_search_or_url_context(self):
        from tools.search_agent import create_enterprise_search_agent

        tools = create_enterprise_search_agent("my-ds").tools
        assert google_search not in tools
        assert url_context not in tools


class TestCreateSearchAgentConvenienceWrapper:
    """create_search_agent() dispatches to web or enterprise based on datastore_id."""

    def test_no_datastore_returns_web_agent(self):
        from tools.search_agent import create_search_agent

        assert create_search_agent().name == "web_search_agent"

    def test_with_datastore_returns_enterprise_agent(self):
        from tools.search_agent import create_search_agent

        assert create_search_agent(datastore_id="my-ds").name == "enterprise_search_agent"


class TestResolveSearchTools:
    """_resolve_search_tools returns the right AgentTool(s) for each combination."""

    def test_no_search_tools_returns_empty(self):
        from adk.agent import _resolve_search_tools

        assert _resolve_search_tools(["list_documents"], {}) == []

    def test_google_search_only_returns_google_search_agent_tool(self):
        from google.adk.tools.google_search_agent_tool import GoogleSearchAgentTool

        from adk.agent import _resolve_search_tools

        result = _resolve_search_tools(["google_search"], {})
        assert len(result) == 1
        # ADK-native class — propagates grounding metadata to parent session
        assert isinstance(result[0], GoogleSearchAgentTool)
        assert result[0].agent.name == "web_search_agent"

    def test_ai_search_with_datastore_returns_enterprise_agent_tool(self):
        from adk.agent import _resolve_search_tools

        configs = {
            "ai_search": {"datastore_id": "projects/p/locations/eu/collections/default_collection/dataStores/ds"}
        }
        result = _resolve_search_tools(["ai_search"], configs)
        assert len(result) == 1
        assert isinstance(result[0], AgentTool)
        assert result[0].agent.name == "enterprise_search_agent"
        assert result[0].propagate_grounding_metadata is True

    def test_ai_search_without_datastore_skips_and_warns(self, caplog):
        import logging

        from adk.agent import _resolve_search_tools

        with caplog.at_level(logging.WARNING):
            result = _resolve_search_tools(["ai_search"], {})
        assert result == []
        assert any("datastore_id" in r.message for r in caplog.records)

    def test_both_returns_two_agent_tools(self):
        from adk.agent import _resolve_search_tools

        configs = {"ai_search": {"datastore_id": "my-ds"}}
        result = _resolve_search_tools(["google_search", "ai_search"], configs)
        assert len(result) == 2
        names = {r.agent.name for r in result}
        assert names == {"web_search_agent", "enterprise_search_agent"}
