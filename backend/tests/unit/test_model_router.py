"""Unit tests for resolve_model() (AGENT-FACTORY M1).

Model IDs coming from SkillConfig.skill_metadata.model are dispatched to the
correct ADK wrapper. Three provider families:
  - Gemini: gemini-*  -> google.adk.models.Gemini
  - Claude: claude-*  -> google.adk.models.Claude
  - OpenAI: gpt-* / o3*  -> google.adk.models.lite_llm.LiteLlm (openai/ prefix)
"""

from __future__ import annotations

import pytest
from google.adk.models import Claude, Gemini
from google.adk.models.lite_llm import LiteLlm

from adk.agent import resolve_model


def test_gemini_model_returns_gemini_wrapper():
    model = resolve_model("gemini-2.5-flash")
    assert isinstance(model, Gemini)
    assert model.model == "gemini-2.5-flash"


def test_gemini_pro_model_returns_gemini_wrapper():
    model = resolve_model("gemini-2.5-pro")
    assert isinstance(model, Gemini)


def test_claude_model_returns_claude_wrapper():
    model = resolve_model("claude-opus-4-7")
    assert isinstance(model, Claude)


def test_openai_gpt_model_returns_litellm_with_openai_prefix():
    model = resolve_model("gpt-4o")
    assert isinstance(model, LiteLlm)
    # LiteLlm stores the openai/-prefixed id
    assert "openai/gpt-4o" in str(model.model)


def test_openai_o3_model_returns_litellm():
    model = resolve_model("o3-mini")
    assert isinstance(model, LiteLlm)
    assert "openai/o3-mini" in str(model.model)


def test_unsupported_model_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported model"):
        resolve_model("mistral-large")


def test_empty_model_id_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported model"):
        resolve_model("")
