"""Code execution sub-agent for non-Gemini skill agents.

Gemini agents receive BuiltInCodeExecutor directly on their LlmAgent instance.
Claude and OpenAI agents cannot use BuiltInCodeExecutor (Gemini-only), so they
delegate code execution to this Gemini-backed sub-agent via AgentTool.
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor

_CODE_AGENT_MODEL = os.environ.get("CODE_AGENT_MODEL", "gemini-2.5-flash")


def create_code_agent() -> LlmAgent:
    """Return a Gemini LlmAgent with BuiltInCodeExecutor for code execution tasks.

    Used as the backing agent for AgentTool when the parent skill agent runs on
    Claude or OpenAI (which cannot use BuiltInCodeExecutor natively).
    """
    return LlmAgent(
        name="code_agent",
        model=_CODE_AGENT_MODEL,
        instruction=(
            "You are a code execution assistant. "
            "Execute the code the user provides and return the output. "
            "If the code produces an error, include the full error message in your response."
        ),
        code_executor=BuiltInCodeExecutor(),
    )
