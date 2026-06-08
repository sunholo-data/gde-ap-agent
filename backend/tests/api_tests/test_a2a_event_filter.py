"""Tests for the A2A event filter interceptor.

The filter v3 covers two real-world wire shapes the new ADK executor
produces (the v1 + v2 designs got both wrong):

  - Visible text content rides on TaskArtifactUpdateEvents, NOT status
    updates (caught live 2026-06-08T18:33 — first deploy dropped zero
    events because it only inspected status events)
  - Runtime author names are UUID-derived via _safe_agent_name(skill_id),
    not the SKILL.md `name` field (caught same turn — second deploy still
    dropped zero events because the drop-set used kebab/underscored
    `invoice-extractor` literals that never matched)

Resolved by deriving the intermediate-author set from the agent
topology at interceptor build time: any SequentialAgent's
non-terminal sub-agents are intermediate. The terminal sub-agent
(e.g. ap-poster) and the root LlmAgent's own events pass through.

Tests use synthetic A2A events + a stubbed ADK event carrying only an
`author` attribute (filter only reads .author). No real Runner, no
session, no agent loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import pytest

INTERMEDIATES = frozenset({"invoice_extractor", "ap_validator"})


def _text_status_event(text: str) -> Any:
    """TaskStatusUpdateEvent carrying a TextPart."""
    from a2a.types import Message, Part, Role, TaskState, TaskStatus, TaskStatusUpdateEvent, TextPart

    return TaskStatusUpdateEvent(
        task_id="t1",
        context_id="c1",
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


def _state_only_status_event() -> Any:
    """TaskStatusUpdateEvent with no message — pure state transition."""
    from a2a.types import TaskState, TaskStatus, TaskStatusUpdateEvent

    return TaskStatusUpdateEvent(task_id="t1", context_id="c1", final=False, status=TaskStatus(state=TaskState.working))


def _text_artifact_event(text: str) -> Any:
    """TaskArtifactUpdateEvent carrying a TextPart — this is what the new
    ADK executor produces for visible narrative content."""
    from a2a.types import Artifact, Part, TaskArtifactUpdateEvent, TextPart

    return TaskArtifactUpdateEvent(
        task_id="t1",
        context_id="c1",
        last_chunk=True,
        artifact=Artifact(
            artifact_id=str(uuid.uuid4()),
            parts=[Part(root=TextPart(text=text))],
        ),
    )


def _data_artifact_event() -> Any:
    """TaskArtifactUpdateEvent carrying a DataPart (function_call shape).

    This is the audit-trail event — tool calls, tool results. Must pass
    through regardless of author so judges/auditors can verify the
    pipeline's tool invocations.
    """
    from a2a.types import Artifact, DataPart, Part, TaskArtifactUpdateEvent

    return TaskArtifactUpdateEvent(
        task_id="t1",
        context_id="c1",
        last_chunk=True,
        artifact=Artifact(
            artifact_id=str(uuid.uuid4()),
            parts=[Part(root=DataPart(data={"name": "tool_x", "args": {}}))],
        ),
    )


class _FakeAdkEvent:
    """Minimal stand-in for google.adk.events.Event — filter only reads .author."""

    def __init__(self, author: str | None) -> None:
        self.author = author


def _filter():
    """Build a fresh interceptor with the AP-pipeline drop-set."""
    from protocols.a2a_event_filter import make_event_filter_interceptor

    return make_event_filter_interceptor(INTERMEDIATES)


# ---------------------------------------------------------------------------
# Status-update event filtering
# ---------------------------------------------------------------------------


def test_drops_text_status_event_from_invoice_extractor() -> None:
    interceptor = _filter()
    a2a_evt = _text_status_event("Reading the parsed invoice...")
    adk_evt = _FakeAdkEvent(author="invoice_extractor")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is None


def test_keeps_text_status_event_from_ap_poster() -> None:
    interceptor = _filter()
    a2a_evt = _text_status_event("Verdict is needs_review — routing to finance...")
    adk_evt = _FakeAdkEvent(author="ap_poster")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is a2a_evt


def test_keeps_state_only_event_regardless_of_author() -> None:
    interceptor = _filter()
    a2a_evt = _state_only_status_event()
    adk_evt = _FakeAdkEvent(author="invoice_extractor")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is a2a_evt


# ---------------------------------------------------------------------------
# Artifact-update event filtering (this is where visible text actually lives)
# ---------------------------------------------------------------------------


def test_drops_text_artifact_event_from_intermediate() -> None:
    """Visible narrative text rides on TaskArtifactUpdateEvents in the new
    ADK executor — this is the load-bearing case the filter must handle."""
    interceptor = _filter()
    a2a_evt = _text_artifact_event("Validating the extracted invoice...")
    adk_evt = _FakeAdkEvent(author="ap_validator")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is None


def test_keeps_text_artifact_event_from_ap_poster() -> None:
    interceptor = _filter()
    a2a_evt = _text_artifact_event("Verdict is approved...")
    adk_evt = _FakeAdkEvent(author="ap_poster")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is a2a_evt


def test_keeps_data_artifact_regardless_of_author() -> None:
    """Tool call / function response artifacts must pass through for audit."""
    interceptor = _filter()
    a2a_evt = _data_artifact_event()
    adk_evt = _FakeAdkEvent(author="invoice_extractor")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is a2a_evt


# ---------------------------------------------------------------------------
# Topology derivation
# ---------------------------------------------------------------------------


def test_derives_intermediates_from_sequential_agent() -> None:
    """Walking an LlmAgent → SequentialAgent → [Extract, Validate, Post]
    tree yields {Extract.name, Validate.name} — Post is terminal."""
    from google.adk.agents import LlmAgent, SequentialAgent

    from protocols.a2a_event_filter import derive_intermediate_authors

    extract = LlmAgent(name="invoice_extractor", model="gemini-2.5-flash", instruction="x")
    validate = LlmAgent(name="ap_validator", model="gemini-2.5-flash", instruction="x")
    poster = LlmAgent(name="ap_poster", model="gemini-2.5-flash", instruction="x")
    pipeline = SequentialAgent(name="ap_pipeline", sub_agents=[extract, validate, poster])
    root = LlmAgent(name="ap_orchestrator", model="gemini-2.5-flash", instruction="x", sub_agents=[pipeline])

    result = derive_intermediate_authors(root)
    assert result == frozenset({"invoice_extractor", "ap_validator"})


def test_derives_empty_set_when_no_sequential_agent() -> None:
    """A pure LlmAgent with no SequentialAgent sub-tree contributes no intermediates."""
    from google.adk.agents import LlmAgent

    from protocols.a2a_event_filter import derive_intermediate_authors

    agent = LlmAgent(name="solo", model="gemini-2.5-flash", instruction="x")
    assert derive_intermediate_authors(agent) == frozenset()


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_fail_open_on_exception() -> None:
    """A malformed event whose attribute access throws is returned unchanged."""
    interceptor = _filter()

    class _Broken:
        @property
        def artifact(self) -> Any:
            raise RuntimeError("decode error")

        @property
        def status(self) -> Any:
            raise RuntimeError("decode error")

    broken = _Broken()
    adk_evt = _FakeAdkEvent(author="invoice_extractor")

    result = asyncio.run(interceptor.after_event(None, broken, adk_evt))
    assert result is broken


def test_empty_drop_set_keeps_every_event() -> None:
    """If no intermediates were detected, the filter is a passthrough."""
    from protocols.a2a_event_filter import make_event_filter_interceptor

    interceptor = make_event_filter_interceptor(frozenset())
    a2a_evt = _text_artifact_event("anything")
    adk_evt = _FakeAdkEvent(author="invoice_extractor")

    result = asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))
    assert result is a2a_evt


def test_logs_warning_on_drop(caplog: pytest.LogCaptureFixture) -> None:
    interceptor = _filter()
    a2a_evt = _text_artifact_event("Validating the extracted invoice INV-2026-042...")
    adk_evt = _FakeAdkEvent(author="ap_validator")

    with caplog.at_level(logging.WARNING, logger="protocols.a2a_event_filter"):
        asyncio.run(interceptor.after_event(None, a2a_evt, adk_evt))

    drop_records = [r for r in caplog.records if "a2a event filter: dropped" in r.getMessage()]
    assert len(drop_records) == 1
    assert "author=ap_validator" in drop_records[0].getMessage()
    assert "Validating" in drop_records[0].getMessage()
