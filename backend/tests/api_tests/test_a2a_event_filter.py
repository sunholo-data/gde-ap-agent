"""Tests for the A2A event filter interceptor.

Eight tests covering the contract `protocols.a2a_event_filter` establishes:
  - Text events from invoice-extractor are dropped
  - Text events from ap-validator are dropped
  - Text events from ap-poster pass through (it emits the verdict)
  - Text events from ap-orchestrator pass through (root agent)
  - TaskArtifactUpdateEvents pass through regardless of author (audit trail)
  - TaskStatusUpdateEvents without text (state-only) pass through
  - Exceptions in the filter fail open (event returns unchanged)
  - The drop emits a structured WARNING log line

The filter is pure-functional — no I/O, no async runner, no session
service — so tests construct synthetic A2A + ADK events directly.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import pytest


def _text_status_event(text: str, *, task_id: str = "t1", context_id: str = "c1") -> Any:
    """Build a TaskStatusUpdateEvent carrying a single text part."""
    from a2a.types import Message, Part, Role, TaskState, TaskStatus, TaskStatusUpdateEvent, TextPart

    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        final=False,
        status=TaskStatus(
            state=TaskState.working,
            message=Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=text))],
            ),
        ),
    )


def _state_only_status_event(*, task_id: str = "t1", context_id: str = "c1") -> Any:
    """Build a TaskStatusUpdateEvent with no message (pure state transition)."""
    from a2a.types import TaskState, TaskStatus, TaskStatusUpdateEvent

    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        final=False,
        status=TaskStatus(state=TaskState.working),
    )


def _artifact_update_event(*, task_id: str = "t1", context_id: str = "c1") -> Any:
    """Build a TaskArtifactUpdateEvent (tool result / audit artifact)."""
    from a2a.types import Artifact, Part, TaskArtifactUpdateEvent, TextPart

    return TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        last_chunk=False,
        artifact=Artifact(
            artifact_id=str(uuid.uuid4()),
            parts=[Part(root=TextPart(text="tool_result_blob"))],
        ),
    )


class _FakeAdkEvent:
    """Minimal stand-in for google.adk.events.Event.

    The filter only reads `.author`. Real ADK Events have many more
    fields; the filter doesn't care about them.
    """

    def __init__(self, author: str | None) -> None:
        self.author = author


def test_drops_text_event_from_invoice_extractor() -> None:
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _text_status_event("Reading the parsed invoice and extracting...")
    adk_evt = _FakeAdkEvent(author="invoice-extractor")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))
    assert result is None, "invoice-extractor text events must be dropped"


def test_drops_text_event_from_ap_validator() -> None:
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _text_status_event("Validating the extracted invoice against vendor master...")
    adk_evt = _FakeAdkEvent(author="ap-validator")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))
    assert result is None, "ap-validator text events must be dropped"


def test_keeps_text_event_from_ap_poster() -> None:
    """ap-poster is the terminal specialist — its verdict text MUST flow through."""
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _text_status_event("Verdict is needs_review — routing to finance...")
    adk_evt = _FakeAdkEvent(author="ap-poster")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))
    assert result is a2a_evt, "ap-poster text events must pass through unchanged"


def test_keeps_text_event_from_ap_orchestrator() -> None:
    """The root orchestrator must always be forwarded."""
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _text_status_event("orchestrator wrap-up text")
    adk_evt = _FakeAdkEvent(author="ap-orchestrator")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))
    assert result is a2a_evt


def test_keeps_artifact_update_event_regardless_of_author() -> None:
    """Tool calls / results are audit signals. NEVER filter them."""
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _artifact_update_event()
    # Even authored by an "intermediate" specialist, artifact events pass through
    adk_evt = _FakeAdkEvent(author="invoice-extractor")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))
    assert result is a2a_evt, "artifact events must pass through unconditionally"


def test_keeps_state_only_event_without_text() -> None:
    """State transitions (working / submitted / completed) without text must pass."""
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _state_only_status_event()
    # Even authored by an intermediate specialist — state-only events aren't visible content
    adk_evt = _FakeAdkEvent(author="invoice-extractor")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))
    assert result is a2a_evt


def test_fail_open_on_exception() -> None:
    """If the filter explodes on a malformed event, return the event unchanged."""
    from protocols.a2a_event_filter import _after_event

    class _Broken:
        @property
        def status(self) -> Any:
            raise RuntimeError("simulated decode error")

    broken = _Broken()
    adk_evt = _FakeAdkEvent(author="invoice-extractor")

    result = asyncio.run(_after_event(executor_context=None, a2a_event=broken, adk_event=adk_evt))
    assert result is broken, "fail-open: malformed event passes through unchanged"


def test_logs_warning_on_drop(caplog: pytest.LogCaptureFixture) -> None:
    """Each drop emits one structured WARNING line so the count is observable."""
    from protocols.a2a_event_filter import _after_event

    a2a_evt = _text_status_event("Validating the extracted invoice...")
    adk_evt = _FakeAdkEvent(author="ap-validator")

    with caplog.at_level(logging.WARNING, logger="protocols.a2a_event_filter"):
        asyncio.run(_after_event(executor_context=None, a2a_event=a2a_evt, adk_event=adk_evt))

    drop_records = [r for r in caplog.records if "a2a event filter: dropped" in r.getMessage()]
    assert len(drop_records) == 1, f"expected 1 drop log line, got {len(drop_records)}: {caplog.records!r}"
    msg = drop_records[0].getMessage()
    assert "author=ap-validator" in msg
    assert "Validating" in msg, "log line must include a text preview for debugging"
