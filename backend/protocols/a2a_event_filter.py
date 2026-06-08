"""A2A intermediate-event filter interceptor.

Mounted via `A2aAgentExecutorConfig(execute_interceptors=[...])` on the
A2A executor in `protocols.a2a_invocation`. Runs as an `after_event`
hook on every A2A event the executor produces.

Why we need this:

  The AP pipeline is wired as a SequentialAgent (`ap-pipeline`) of three
  LlmAgent specialists: `invoice-extractor`, `ap-validator`, `ap-poster`.
  Each specialist emits ADK events as it processes its turn — including
  intent-narration text events like "Reading the parsed invoice and
  extracting vendor, line items, and totals." These are Gemini's
  "thinking out loud" preamble before tool calls.

  ADK's `convert_event_to_a2a_events` projects every ADK event into the
  A2A event queue. Peers (Gemini Enterprise) receive the stream of
  text-bearing TaskStatusUpdateEvents and concatenate them into the
  chat bubble — producing a wall of specialist narration plus the
  final verdict from `ap-poster`. The narration is internal-monologue
  noise; the peer should only see the verdict.

What this interceptor does:

  Returns None for every text-bearing TaskStatusUpdateEvent whose ADK
  source event was authored by `invoice-extractor` or `ap-validator`.
  ADK's executor treats None as "drop this event" — it never reaches
  the peer's SSE stream.

  Keeps:
    - All events from `ap-orchestrator`, `ap-pipeline`, `ap-poster`,
      and the special `"user"` author
    - All TaskArtifactUpdateEvents regardless of author — these are
      tool call/result artifacts attached to the task for audit, not
      chat content
    - All TaskStatusUpdateEvents without text content (state
      transitions like submitted/working/completed)

  Drops:
    - TaskStatusUpdateEvents whose `status.message.parts` contains at
      least one text part AND whose source ADK event was authored by
      `invoice-extractor` or `ap-validator`

Configuration:
  None. v1 hard-codes the AP-pipeline specialist names. Forks with
  different pipelines can copy the pattern and adjust
  `_INTERMEDIATE_SPECIALIST_AUTHORS`.

Failure mode:
  Fail-open. Any exception inside `_after_event` returns the event
  unchanged (no drop on filter error). The peer sees the unfiltered
  event rather than nothing — degrading to current pre-filter behaviour
  rather than silence.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


# Skill names of sub-agents whose text-bearing events should NOT reach
# the A2A peer. Source of truth: `backend/adk/agent.py:305`
# (`_AP_SPECIALIST_STAGE_LABELS`). `ap-poster` is intentionally absent —
# it emits the final verdict and must be preserved.
#
# We include BOTH kebab and underscored forms because ADK's LlmAgent
# name validator requires `^[a-zA-Z_][a-zA-Z0-9_]*$` and
# `_safe_agent_name()` in `backend/adk/agent.py` substitutes `-` → `_`.
# At runtime, `event.author` carries the ADK-validated form (e.g.
# `invoice_extractor`), but tests and external probes often use the
# canonical SKILL.md name (`invoice-extractor`). Accepting both makes
# the filter robust to either source. Caught live 2026-06-08T15:59 —
# first deploy of this filter dropped 0 events because the kebab form
# never matched the underscored runtime author.
_INTERMEDIATE_SPECIALIST_AUTHORS: frozenset[str] = frozenset(
    {
        "invoice-extractor",
        "invoice_extractor",
        "ap-validator",
        "ap_validator",
    }
)


def _event_has_visible_text(a2a_event: Any) -> bool:
    """Return True iff the A2A event is a text-bearing TaskStatusUpdateEvent.

    Only text-bearing TaskStatusUpdateEvents surface as visible content
    in the peer's chat bubble. Artifact updates and state-only updates
    are out-of-band signals and should never be filtered.
    """
    from a2a.types import TaskStatusUpdateEvent

    if not isinstance(a2a_event, TaskStatusUpdateEvent):
        return False
    status = getattr(a2a_event, "status", None)
    if status is None:
        return False
    msg = getattr(status, "message", None)
    if msg is None:
        return False
    parts = getattr(msg, "parts", None) or []
    for part in parts:
        # Pydantic Part has .root which is one of TextPart | FilePart | DataPart
        root = getattr(part, "root", part)
        kind = getattr(root, "kind", None)
        if kind == "text":
            return True
    return False


def _should_drop(a2a_event: Any, adk_event: Any) -> bool:
    """Decide whether to filter this event out of the peer-bound stream."""
    if not _event_has_visible_text(a2a_event):
        return False
    author = getattr(adk_event, "author", None)
    if not author:
        return False
    return author in _INTERMEDIATE_SPECIALIST_AUTHORS


def _extract_text_preview(a2a_event: Any) -> str:
    """Best-effort short preview of the dropped text for logging."""
    try:
        msg = a2a_event.status.message
        for part in msg.parts:
            root = getattr(part, "root", part)
            text = getattr(root, "text", None)
            if text:
                return text[:80]
    except Exception:
        return ""
    return ""


async def _after_event(executor_context: Any, a2a_event: Any, adk_event: Any) -> Any:
    """Filter intermediate specialist narration before it reaches the peer.

    Returns the event unchanged unless it matches the drop rule, in which
    case returns None (ADK's executor drops the event from the queue).
    On any exception, returns the event unchanged (fail-open).
    """
    # Observation log: every event passing through the filter emits one
    # line capturing author + visible-text flag. Cardinality is bounded
    # (~20 events per pipeline turn), kept as a permanent debugging
    # surface for forks: without it, you can't tell what author strings
    # are flowing or whether the kept/dropped balance matches design.
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
        if _should_drop(a2a_event, adk_event):
            author = getattr(adk_event, "author", "?")
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


def make_event_filter_interceptor() -> Any:
    """Return an ExecuteInterceptor that filters intermediate AP specialist text events.

    Composes cleanly with the file-extraction interceptor: this one only
    sets `after_event`, the other only sets `before_agent`.
    """
    from google.adk.a2a.executor.config import ExecuteInterceptor

    return ExecuteInterceptor(after_event=_after_event)
