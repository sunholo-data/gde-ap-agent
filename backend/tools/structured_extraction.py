"""Structured extraction — after_agent callback for schema-driven data extraction.

SCHEMA-ENFORCE sprint: when a SKILL.md declares ``metadata.extraction_schema``
(named ref or inline JSON Schema), the before-agent setter in
``adk/agent.py`` writes the resolved schema to ``app:extraction_schema``.
This callback then fires after the agent's response, runs a
schema-constrained Gemini extraction over the document blocks the agent
read via ``get_document_content(mode="blocks")``, validates the output
via ``jsonschema.Draft202012Validator`` server-side, and **appends a
``types.Content`` to the agent's response** containing the validated
JSON — making the structurally-guaranteed payload the last text message
in the AG-UI stream.

Wire-up in ``adk/agent.py``:

    after_agent_callbacks=[..., structured_extraction_callback]

Operating on blocks JSON (not markdown) preserves table structure, tracked
changes, and section hierarchy — critical for accurate financial,
contract, and invoice extraction.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.adk.agents.callback_context import CallbackContext
from google.genai import types as genai_types
from jsonschema import Draft202012Validator

log = logging.getLogger(__name__)

_EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-2.5-flash")
_LARGE_OUTPUT_THRESHOLD = 50_000
# Single source of truth for the JSON mime literal (used in multiple Gemini configs).
_JSON_MIME = "application/json"
_STATE_EXTRACTION_RESULT = "temp:extraction_result"
_STATE_VALIDATION_ERRORS = "temp:extraction_validation_errors"
_STATE_EXTRACTION_SCHEMA = "app:extraction_schema"
_STATE_DOCUMENT_BLOCKS = "temp:document_blocks"
_STATE_DOCUMENT_ID = "temp:document_id"


async def structured_extraction_callback(callback_context: CallbackContext) -> Any:
    """After-agent callback: extract structured data when a schema is set.

    Reads:
      app:extraction_schema  — JSON Schema dict (set by before-agent setter)
      temp:document_blocks   — Blocks JSON string (set by get_document_content mode="blocks")

    Writes (always):
      temp:extraction_result            — Validated JSON string OR error envelope
    Writes (on validation failure only):
      temp:extraction_validation_errors — List of jsonschema violation strings

    Returns:
      genai_types.Content with the validated JSON when extraction succeeded,
      otherwise None. ADK appends the returned Content as an additional
      agent response — so downstream consumers (structured_invocation,
      ap-validator transfer result) see the schema-enforced payload as the
      final TEXT_MESSAGE_CONTENT in the AG-UI stream.
    """
    schema = callback_context.state.get(_STATE_EXTRACTION_SCHEMA)
    if not schema:
        return None

    blocks_json = callback_context.state.get(_STATE_DOCUMENT_BLOCKS)
    if not blocks_json:
        log.debug("structured_extraction: app:extraction_schema is set but no temp:document_blocks found; skipping")
        return None

    doc_id = callback_context.state.get(_STATE_DOCUMENT_ID, "unknown")
    log.info("structured_extraction: running schema-enforced extraction for doc %s", doc_id)

    # Gemini constrained-decoding pass
    try:
        result_json = await _run_extraction(blocks_json, schema)
    except Exception as exc:
        log.warning("structured_extraction: extraction failed for doc %s: %s", doc_id, exc)
        callback_context.state[_STATE_EXTRACTION_RESULT] = json.dumps(
            {"error": f"Extraction failed: {exc}", "doc_id": doc_id}
        )
        return None

    # Server-side jsonschema validation as defence-in-depth — Gemini's
    # constrained decoding doesn't always perfectly enforce Draft 2020-12
    # constructs like `if/then/else` (used by ap_posting_record).
    schema_dict = schema if isinstance(schema, dict) else None
    validation_errors = _validate_against_schema(result_json, schema_dict)
    if validation_errors:
        log.warning(
            "structured_extraction.validation_failed skill_doc=%s schema=%s errors=%d",
            doc_id,
            _schema_label(schema_dict),
            len(validation_errors),
        )
        callback_context.state[_STATE_VALIDATION_ERRORS] = validation_errors
    else:
        callback_context.state.pop(_STATE_VALIDATION_ERRORS, None)

    # Persist the result — large outputs go to an artifact + a pointer.
    if len(result_json) > _LARGE_OUTPUT_THRESHOLD:
        artifact_id = f"extraction_{doc_id}"
        try:
            part = genai_types.Part.from_text(result_json)
            await callback_context.save_artifact(filename=artifact_id, artifact=part)
            callback_context.state[_STATE_EXTRACTION_RESULT] = json.dumps(
                {"artifact_id": artifact_id, "doc_id": doc_id, "truncated": True}
            )
            log.info("structured_extraction: large result saved as artifact %s", artifact_id)
        except Exception as exc:
            log.warning("structured_extraction: artifact save failed: %s", exc)
            callback_context.state[_STATE_EXTRACTION_RESULT] = result_json
    else:
        callback_context.state[_STATE_EXTRACTION_RESULT] = result_json

    # Append the validated JSON as the agent's final text message. ADK's
    # after_agent_callback contract treats a returned Content as an
    # additional response event — so the AG-UI stream's last
    # TEXT_MESSAGE_CONTENT is the schema-enforced payload. Downstream
    # consumers (structured_invocation, ap-validator transfer result)
    # JSON.parse this directly.
    #
    # Visual rendering (turning this JSON into a styled Card so the user
    # doesn't see a code block) is the frontend's job — see
    # frontend/src/components/chat/JsonCardBuilder.ts. We tried
    # synthesising a function_call + function_response Part pair here on
    # 2026-06-02 to fake an A2UI tool result; ADK / the genai SDK strip
    # function_response Parts from role="model" Content (function_response
    # is semantically a tool→model message, not a model→user message), so
    # only the function_call survived and the frontend saw a tool call
    # that never resolved. Moving the rendering frontend-side avoids the
    # need for that synthesis entirely.
    return genai_types.Content(
        role="model",
        parts=[genai_types.Part.from_text(text=result_json)],
    )


def _schema_label(schema: dict | None) -> str:
    """Best-effort name for log lines — falls back to <inline> when no title."""
    if schema is None:
        return "<none>"
    return str(schema.get("title") or schema.get("description") or "<inline>")[:40]


def _validate_against_schema(result_json: str, schema: dict | None) -> list[str]:
    """Run Draft 2020-12 validation over the extraction output.

    Returns a list of human-readable error strings (empty when valid).
    `if/then/else`, `oneOf`/`anyOf`, and other constructs not in the
    Gemini constrained-decoding subset are enforced here — defence in
    depth on top of Gemini's best-effort schema adherence.
    """
    if schema is None:
        return []
    try:
        parsed = json.loads(result_json)
    except json.JSONDecodeError as exc:
        return [f"<root>: invalid JSON returned by extraction model: {exc}"]
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(parsed), key=lambda e: list(e.absolute_path))
    return [_format_violation(e) for e in errors]


def _format_violation(err: Any) -> str:
    path = ".".join(str(p) for p in err.absolute_path) or "<root>"
    return f"{path}: {err.message}"


def _extraction_config_for_model(model_id: str, schema: dict | None) -> dict:
    """Return the Gemini generate-content config shape for the model family.

    Verified empirically against Vertex AI on 2026-06-02:
      - gemini-2.5-flash in europe-west1 + 2.x config → OK
      - gemini-3.5-flash in global + 2.x config → OK
      - gemini-3.1-flash-lite in global + 2.x config → OK
      - gemini-3-flash (preview tier) → 404 NOT_FOUND even in global

    The ai.google.dev/gemini-api/docs/structured-output page describes a
    new `response_format: {text: {mime_type, schema}}` shape for Gemini
    3.x, but google-genai 1.73.1's GenerateContentConfig Pydantic model
    rejects that key (`extra inputs not permitted`). Until the SDK
    catches up, both 2.x and 3.x models use the legacy
    `response_mime_type` + `response_schema` config — Gemini accepts it
    cleanly for both families.

    Kept as a helper (rather than inlined) for the eventual SDK upgrade:
    when the new shape ships, branch on `is_gemini_3_or_above(model_id)`.
    For now, model_id is preserved for future use and observability.
    """
    _ = model_id  # reserved for the eventual SDK-supports-response_format branch
    if schema is None:
        return {"response_mime_type": _JSON_MIME}
    return {"response_mime_type": _JSON_MIME, "response_schema": schema}


async def _run_extraction(blocks_json: str, schema: dict | str) -> str:
    """Run Gemini extraction over blocks JSON with the given schema.

    Args:
        blocks_json: JSON string containing document blocks.
        schema: JSON Schema dict or pre-serialized JSON string describing target fields.

    Returns:
        Extracted data as a JSON string.
    """
    if isinstance(schema, str):
        schema_str = schema
        schema_dict: dict | None = None
    else:
        schema_str = json.dumps(schema, indent=2)
        schema_dict = schema

    prompt = (
        "You are a precise data extraction assistant. "
        "Extract structured data from the document blocks below according to the JSON schema provided.\n"
        "Return ONLY valid JSON that matches the schema exactly. "
        "Do not add explanation or markdown fencing.\n\n"
        f"JSON Schema:\n{schema_str}\n\n"
        f"Document blocks (JSON):\n{blocks_json}"
    )

    config = _extraction_config_for_model(_EXTRACTION_MODEL, schema_dict)

    client = genai.Client(vertexai=True)
    response = await client.aio.models.generate_content(
        model=_EXTRACTION_MODEL,
        contents=prompt,
        config=config,
    )

    text = response.text or ""
    if not text:
        raise ValueError("Gemini returned empty extraction response")

    json.loads(text)
    return text
