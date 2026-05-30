"""Tests for tools/code_execution/agent.py and agent.py code executor wiring."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor


class TestCreateCodeAgent:
    def test_returns_llm_agent(self):
        from tools.code_execution.agent import create_code_agent

        agent = create_code_agent()
        assert isinstance(agent, LlmAgent)

    def test_agent_name(self):
        from tools.code_execution.agent import create_code_agent

        agent = create_code_agent()
        assert agent.name == "code_agent"

    def test_has_built_in_code_executor(self):
        from tools.code_execution.agent import create_code_agent

        agent = create_code_agent()
        assert isinstance(agent.code_executor, BuiltInCodeExecutor)

    def test_uses_gemini_model(self):
        from tools.code_execution.agent import create_code_agent

        agent = create_code_agent()
        assert "gemini" in str(agent.model).lower()


class TestResolveCodeExecutor:
    def test_no_code_execution_tool_returns_none_and_empty(self):
        from adk.agent import _resolve_code_executor

        executor, tools = _resolve_code_executor(["list_documents"], "gemini-2.5-flash")
        assert executor is None
        assert tools == []

    def test_gemini_gets_built_in_executor(self):
        from adk.agent import _resolve_code_executor

        executor, tools = _resolve_code_executor(["code_execution"], "gemini-2.5-flash")
        assert isinstance(executor, BuiltInCodeExecutor)
        assert tools == []

    def test_claude_gets_agent_tool_not_executor(self):
        from google.adk.tools import AgentTool

        from adk.agent import _resolve_code_executor

        executor, tools = _resolve_code_executor(["code_execution"], "claude-3-5-sonnet")
        assert executor is None
        assert len(tools) == 1
        assert isinstance(tools[0], AgentTool)

    def test_openai_gets_agent_tool_not_executor(self):
        from google.adk.tools import AgentTool

        from adk.agent import _resolve_code_executor

        executor, tools = _resolve_code_executor(["code_execution"], "gpt-4o")
        assert executor is None
        assert len(tools) == 1
        assert isinstance(tools[0], AgentTool)
