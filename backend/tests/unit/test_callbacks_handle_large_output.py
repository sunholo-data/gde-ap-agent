"""Unit tests for M3 ADK callbacks (AGENT-FACTORY M3).

* `_handle_large_output` — `after_tool_callback`. Keeps small tool
  responses as-is; for >50K char responses saves an ADK artifact via
  `tool_context.save_artifact(...)` and returns a pointer string so the
  model sees a short reference instead of megabytes of text.
* `make_before_agent(skill_id)` — `before_agent_callback` factory.
  Returns a callback that annotates the current OTEL span with
  `skill_id` and (if present on session state) `routing_choice`.
* `_after_agent` — documented no-op reserved for v6.1 structured
  extraction (not tested beyond "it's a callable that returns None").
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from adk.callbacks import _after_agent, _handle_large_output, make_before_agent

# --- _handle_large_output ---


def _mk_tool_context() -> MagicMock:
    ctx = MagicMock()
    ctx.save_artifact = MagicMock()
    return ctx


def test_handle_large_output_passes_small_response_through():
    ctx = _mk_tool_context()
    resp = {"result": "small"}
    out = _handle_large_output(tool=MagicMock(name="search"), args={}, tool_context=ctx, tool_response=resp)
    # Small response should come back unchanged; no artifact saved.
    assert out is resp or out == resp
    ctx.save_artifact.assert_not_called()


def test_handle_large_output_saves_artifact_for_large_response():
    ctx = _mk_tool_context()
    # 60K chars — well over the 50K threshold.
    big_text = "x" * 60_000
    out = _handle_large_output(tool=MagicMock(name="big_search"), args={}, tool_context=ctx, tool_response=big_text)
    # Should return a string (not the original), which is the pointer, and
    # must have called save_artifact exactly once.
    assert isinstance(out, str)
    assert out is not big_text
    assert ctx.save_artifact.call_count == 1


def test_handle_large_output_pointer_mentions_artifact():
    ctx = _mk_tool_context()
    big_text = "y" * 60_000
    out = _handle_large_output(tool=MagicMock(name="big_search"), args={}, tool_context=ctx, tool_response=big_text)
    # Pointer should be informative enough for the model to understand
    # that the full response is saved as an artifact.
    assert "artifact" in out.lower()


def test_handle_large_output_threshold_is_50k_chars():
    ctx = _mk_tool_context()
    # Exactly 50_000 characters — at threshold, should pass through.
    at_threshold = "z" * 50_000
    out = _handle_large_output(tool=MagicMock(name="s"), args={}, tool_context=ctx, tool_response=at_threshold)
    ctx.save_artifact.assert_not_called()
    assert out == at_threshold or out is at_threshold


# --- make_before_agent ---


def test_make_before_agent_returns_callable():
    cb = make_before_agent("my-skill-id")
    assert callable(cb)


def test_before_agent_sets_skill_id_on_current_span():
    cb = make_before_agent("my-skill-id")
    # Mock the OTEL span so the callback can set attributes on it.
    mock_span = MagicMock()
    ctx = MagicMock()
    ctx.state = {}
    from unittest.mock import patch

    with patch("adk.callbacks.trace.get_current_span", return_value=mock_span):
        cb(callback_context=ctx)  # ADK calls by keyword; parameter name is enforced.
    mock_span.set_attribute.assert_any_call("skill_id", "my-skill-id")


def test_before_agent_sets_routing_choice_when_present_in_state():
    cb = make_before_agent("skill-1")
    mock_span = MagicMock()
    ctx = MagicMock()
    ctx.state = {"routing_choice": "thinking"}
    from unittest.mock import patch

    with patch("adk.callbacks.trace.get_current_span", return_value=mock_span):
        cb(callback_context=ctx)  # ADK calls by keyword; parameter name is enforced.
    mock_span.set_attribute.assert_any_call("routing_choice", "thinking")


def test_before_agent_skips_routing_choice_when_absent():
    cb = make_before_agent("skill-1")
    mock_span = MagicMock()
    ctx = MagicMock()
    ctx.state = {}
    from unittest.mock import patch

    with patch("adk.callbacks.trace.get_current_span", return_value=mock_span):
        cb(callback_context=ctx)  # ADK calls by keyword; parameter name is enforced.
    # Only skill_id should be set; no routing_choice.
    call_args = [c.args for c in mock_span.set_attribute.call_args_list]
    keys = {a[0] for a in call_args}
    assert "skill_id" in keys
    assert "routing_choice" not in keys


# --- _after_agent ---


def test_after_agent_is_noop_returning_none():
    # Placeholder for v6.1 structured extraction. Must be a callable that
    # accepts a CallbackContext and returns None without touching state.
    ctx = SimpleNamespace(state={})
    result = _after_agent(callback_context=ctx)
    assert result is None
    assert ctx.state == {}
