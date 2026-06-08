"""A2A intermediate-event filter interceptor.

Mounted via `A2aAgentExecutorConfig(execute_interceptors=[...])` on the
A2A executor in `protocols.a2a_invocation`. Runs as an `after_event`
hook on every A2A event the executor produces.

Why we need this
----------------

The AP pipeline is wired as a SequentialAgent (`ap-pipeline`) of three
LlmAgent specialists: `invoice-extractor`, `ap-validator`, `ap-poster`.
Each specialist emits ADK events as it processes its turn — including
intent-narration text events like "Reading the parsed invoice and
extracting vendor, line items, and totals." These are Gemini's
"thinking out loud" preamble before tool calls.

ADK's new-version event converter (`convert_event_to_a2a_events_impl`
in `google.adk.a2a.converters.from_adk_event`, used when
`force_new_version=True`) projects every ADK event with content into a
`TaskArtifactUpdateEvent` whose artifact carries the parts. Peers
(Gemini Enterprise) receive the stream of TaskArtifactUpdateEvents and
render their text parts in the chat bubble — producing a wall of
specialist narration plus the final verdict from `ap-poster`. The
narration is internal-monologue noise; the peer should only see the
verdict.

Two non-obvious wire-shape facts established the design through three
buggy iterations:

1. **Visible text rides on TaskArtifactUpdateEvents, not status updates.**
   The new converter only emits TaskStatusUpdateEvents for actions
   without parts. All narrative/verdict content goes via artifact
   updates. Caught 2026-06-08T18:33 — the first filter dropped zero
   events because it only inspected status events.

2. **Runtime author names are UUID-derived.** ADK's LlmAgent name
   validator requires `^[a-zA-Z_][a-zA-Z0-9_]*$`, and
   `_safe_agent_name(skill_id)` in `backend/adk/agent.py` substitutes
   `-` → `_`. With Firestore-backed skills, the skill_id is a UUID
   string — so the actual ADK agent name is `s_<uuid_with_underscores>`,
   not the SKILL.md `name` field. Hardcoding `"invoice-extractor"` or
   `"invoice_extractor"` in the drop-set never matches. Caught
   2026-06-08T18:33 — second iteration still dropped zero events.

What this interceptor does
--------------------------

At startup, walks the agent tree from `runner.agent` and finds every
`SequentialAgent`. For each one, captures the names of `sub_agents[:-1]`
— the intermediate specialists. The LAST `sub_agent[-1]` is the
terminal specialist whose output IS the user-facing answer (e.g.
`ap-poster`'s verdict); never filter it.

At runtime, for every A2A event passing through the executor's after_event
hook, drops events whose:
  - source ADK event's `author` is in the captured intermediates set, AND
  - A2A event carries visible text content (either in a
    TaskArtifactUpdateEvent's `artifact.parts` or a TaskStatusUpdateEvent's
    `status.message.parts`)

Keeps:
  - All events from the root agent and from the terminal specialist of
    any SequentialAgent
  - All events without text content (state transitions, function_call
    DataParts, function_response DataParts, file Parts)

Configuration:
  None. Topology is derived from the runner's agent tree at interceptor
  build time. Forks with different pipelines work automatically as long
  as their intermediate-vs-terminal split is expressed as a
  SequentialAgent.

Failure mode:
  Fail-open. Any exception inside `_after_event` returns the event
  unchanged (no drop on filter error). The peer sees the unfiltered
  event rather than nothing — degrading to current pre-filter behaviour
  rather than silence.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)


def _walk_for_intermediates(agent: Any, seen: set[int] | None = None) -> set[str]:
    """Walk an agent tree depth-first, collecting names of sub-agents that
    sit at non-terminal positions inside any SequentialAgent.

    For a `SequentialAgent` with `sub_agents=[a, b, c]`, returns `{a.name, b.name}`
    (c is terminal — keep). Recurses into each sub-agent. Cycle-safe via
    `id()` membership in `seen`.
    """
    from google.adk.agents import SequentialAgent

    if seen is None:
        seen = set()
    if id(agent) in seen:
        return set()
    seen.add(id(agent))

    intermediates: set[str] = set()
    sub_agents = getattr(agent, "sub_agents", None) or []

    if isinstance(agent, SequentialAgent) and len(sub_agents) >= 2:
        for sub in sub_agents[:-1]:
            name = getattr(sub, "name", None)
            if name:
                intermediates.add(name)

    for sub in sub_agents:
        intermediates |= _walk_for_intermediates(sub, seen)

    return intermediates


def derive_intermediate_authors(root_agent: Any) -> frozenset[str]:
    """Public entry point for the topology walk.

    Returns a frozenset of agent names whose text-bearing events should
    be filtered from the peer-bound A2A stream. Caller logs the result
    at interceptor build time so production has direct evidence of what
    was captured.
    """
    return frozenset(_walk_for_intermediates(root_agent))


def _event_has_visible_text(a2a_event: Any) -> bool:
    """True iff the event carries at least one TextPart in its content.

    Inspects both event shapes the new ADK converter can produce:
      - TaskArtifactUpdateEvent: text rides in `artifact.parts`
      - TaskStatusUpdateEvent: text rides in `status.message.parts`

    Returns False for events with no text-bearing parts (state-only
    status events, function_call/function_response DataParts, file
    parts, code-execution artifacts).
    """
    from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

    if isinstance(a2a_event, TaskArtifactUpdateEvent):
        artifact = getattr(a2a_event, "artifact", None)
        parts = getattr(artifact, "parts", None) or []
    elif isinstance(a2a_event, TaskStatusUpdateEvent):
        status = getattr(a2a_event, "status", None)
        msg = getattr(status, "message", None)
        parts = getattr(msg, "parts", None) or []
    else:
        return False

    for part in parts:
        root = getattr(part, "root", part)
        if getattr(root, "kind", None) == "text":
            return True
    return False


def _extract_text_preview(a2a_event: Any) -> str:
    """Best-effort short preview of dropped text for logging."""
    from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

    try:
        if isinstance(a2a_event, TaskArtifactUpdateEvent):
            parts = a2a_event.artifact.parts
        elif isinstance(a2a_event, TaskStatusUpdateEvent):
            parts = a2a_event.status.message.parts
        else:
            return ""
        for part in parts:
            root = getattr(part, "root", part)
            text = getattr(root, "text", None)
            if text:
                return text[:120]
    except Exception:
        return ""
    return ""


def make_event_filter_interceptor(intermediate_authors: Iterable[str]) -> Any:
    """Return an ExecuteInterceptor that filters text events from intermediate authors.

    Args:
        intermediate_authors: agent names whose visible-text events should
            be filtered. Typically derived from `derive_intermediate_authors(
            runner.agent)`.

    The interceptor sets only `after_event`. Composes cleanly with the
    file-extraction interceptor (which only sets `before_agent`).
    """
    from google.adk.a2a.executor.config import ExecuteInterceptor

    authors_set = frozenset(intermediate_authors)
    if authors_set:
        logger.warning(
            "a2a event filter: armed with %d intermediate author(s): %s",
            len(authors_set),
            sorted(authors_set),
        )
    else:
        logger.warning("a2a event filter: armed with NO intermediate authors — no events will be filtered")

    async def _after_event(executor_context: Any, a2a_event: Any, adk_event: Any) -> Any:
        # Observation log: every event passing through the filter emits
        # one line capturing author + visible-text flag + event type.
        # Cardinality is bounded (~20 lines per pipeline turn), kept as
        # a permanent debugging surface for forks: without it, you can't
        # tell what author strings are flowing or whether the kept/dropped
        # balance matches design.
        try:
            author_seen = getattr(adk_event, "author", "?")
            has_text = _event_has_visible_text(a2a_event)
            evt_type = type(a2a_event).__name__
            logger.warning(
                "a2a event filter: seen author=%s evt=%s text=%s",
                author_seen,
                evt_type,
                has_text,
            )
        except Exception:
            pass

        try:
            if not _event_has_visible_text(a2a_event):
                return a2a_event
            author = getattr(adk_event, "author", None)
            if not author or author not in authors_set:
                return a2a_event
            preview = _extract_text_preview(a2a_event)
            logger.warning(
                "a2a event filter: dropped author=%s text=%r",
                author,
                preview,
            )
            return None
        except Exception as exc:
            logger.warning("a2a event filter: exception in filter (fail-open): %s", exc)
        return a2a_event

    return ExecuteInterceptor(after_event=_after_event)
