"""Structured invocation for specialist skills — Audit View "Run Standalone".

Lets the frontend invoke a specialist (docparse, ap-validator, ap-poster)
directly with a typed input, bypassing the orchestrator. Validates the
input against the skill's ``metadata.structuredInput`` JSON Schema (when
present), runs the agent for one turn, and returns the collected events
as a single JSON response.

This is the audit affordance: a reviewer can re-run a specialist with a
hand-tweaked input to verify behaviour, without having to coax the
orchestrator into making the same call again.

See docs/design/forks/gde-ap-agent/multi-agent-inspector-ux.md
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from auth.access_context import AccessContext
from auth.firebase_auth import User
from skills.skill_config import get_skill
from skills.skill_processor import SkillNotFoundError, process_skill_request

logger = logging.getLogger(__name__)


class StructuredInputInvalidError(Exception):
    """Raised when the input payload fails JSON Schema validation."""

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.message = message
        self.errors = errors


class StructuredInputNotSupportedError(Exception):
    """Raised when the skill doesn't declare a structuredInput schema."""

    def __init__(self, skill_id: str) -> None:
        super().__init__(f"Skill {skill_id!r} does not declare metadata.structuredInput")
        self.skill_id = skill_id


def _resolve_schema(skill_id: str) -> dict[str, Any]:
    skill = get_skill(skill_id)
    if skill is None:
        raise SkillNotFoundError(skill_id)
    schema = skill.skill_metadata.structured_input if skill.skill_metadata else None
    if not isinstance(schema, dict) or not schema:
        raise StructuredInputNotSupportedError(skill_id)
    return schema


def validate_structured_input(skill_id: str, payload: Any) -> None:
    """Validate ``payload`` against the skill's structuredInput schema.

    Raises ``StructuredInputInvalidError`` on failure with human-readable
    error strings suitable for surfacing in the form UI.
    """
    schema = _resolve_schema(skill_id)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = [_format_validation_error(e) for e in errors]
        raise StructuredInputInvalidError("Input failed schema validation", msgs)


def _format_validation_error(err: ValidationError) -> str:
    path = ".".join(str(p) for p in err.absolute_path) or "<root>"
    return f"{path}: {err.message}"


def serialize_input_as_message(payload: Any) -> str:
    """Wrap the structured payload in a small preamble so the agent's
    instruction layer recognises it as audit-view input rather than free
    chat. Specialists are instructed to operate on whatever's in this
    block as their canonical input for the turn.
    """
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return (
        "AUDIT-VIEW STANDALONE INVOCATION\n"
        "The following structured input was supplied by an auditor via the "
        "Audit View panel (bypassing the orchestrator). Treat it as your "
        "canonical input for this turn.\n\n"
        f"```json\n{body}\n```"
    )


async def run_structured_invocation(
    skill_id: str,
    user: User,
    access: AccessContext,
    payload: Any,
    session_id: str | None,
) -> dict[str, Any]:
    """Run one specialist turn with a structured input. Collects every
    AG-UI event and returns the aggregate as a JSON-serialisable dict.

    Returns shape::

        {
          "skill_id": "...",
          "duration_ms": 1234,
          "text": "<concatenated final assistant text>",
          "tool_calls": [{"name": "...", "args": {...}, "result": "..."}, ...],
          "raw_events": [...]   # capped to 200 for response-size safety
        }

    Raises:
        SkillNotFoundError: skill missing or not visible to the caller.
        StructuredInputNotSupportedError: skill has no structuredInput schema.
        StructuredInputInvalidError: payload failed schema validation.
    """
    validate_structured_input(skill_id, payload)
    message = serialize_input_as_message(payload)

    started = time.monotonic()
    raw_events: list[dict[str, Any]] = []
    text_buf: list[str] = []
    tool_calls: dict[str, dict[str, Any]] = {}

    async for event in process_skill_request(
        skill_id=skill_id,
        user=user,
        access=access,
        session_id=session_id,
        message=message,
        # Audit-view runs are intentionally side-effect-free w.r.t. the
        # orchestrator's session: no doc-ids, not a resume.
        document_ids=None,
        resumed_session=False,
    ):
        if len(raw_events) < 200:
            raw_events.append(event)
        et = event.get("type") if isinstance(event, dict) else None
        if et == "TEXT_MESSAGE_CONTENT" and isinstance(event.get("delta"), str):
            text_buf.append(event["delta"])
        elif et == "TOOL_CALL_START":
            tcid = str(event.get("toolCallId") or event.get("id") or "")
            tool_calls[tcid] = {
                "name": event.get("toolCallName") or event.get("name") or "",
                "args": "",
                "result": None,
            }
        elif et == "TOOL_CALL_ARGS":
            tcid = str(event.get("toolCallId") or event.get("id") or "")
            if tcid in tool_calls and isinstance(event.get("delta"), str):
                tool_calls[tcid]["args"] += event["delta"]
        elif et == "TOOL_CALL_RESULT":
            tcid = str(event.get("toolCallId") or event.get("id") or "")
            if tcid in tool_calls:
                tool_calls[tcid]["result"] = event.get("content")

    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "skill_id": skill_id,
        "duration_ms": duration_ms,
        "text": "".join(text_buf),
        "tool_calls": list(tool_calls.values()),
        "raw_events": raw_events,
    }
