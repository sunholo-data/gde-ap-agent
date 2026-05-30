"""Structured extraction — after_agent callback for schema-driven data extraction.

Fires after each agent response. When `app:extraction_schema` is set in session
state AND the agent has populated `temp:document_blocks` (via get_document_content
with mode="blocks"), runs a Gemini extraction pass over the blocks JSON and stores
the result in `temp:extraction_result`.

Operating on blocks JSON (not markdown) preserves table structure, tracked changes,
and section hierarchy — critical for accurate financial, contract, and invoice extraction.

Wire-up in adk/agent.py:
    after_agent_callbacks=[..., structured_extraction_callback]
"""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.adk.agents.callback_context import CallbackContext
from google.genai import types as genai_types

log = logging.getLogger(__name__)

_EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-2.5-flash")
_LARGE_OUTPUT_THRESHOLD = 50_000


async def structured_extraction_callback(callback_context: CallbackContext) -> None:
    """After-agent callback: extract structured data when a schema is set.

    Reads:
      app:extraction_schema  — JSON Schema dict (set by skill config or frontend)
      temp:document_blocks   — Blocks JSON string (set by get_document_content mode="blocks")

    Writes:
      temp:extraction_result — Extracted JSON string (or error description)

    Returns None in all cases — the extraction result is communicated via session state,
    not by replacing the agent response.
    """
    schema = callback_context.state.get("app:extraction_schema")
    if not schema:
        return None

    blocks_json = callback_context.state.get("temp:document_blocks")
    if not blocks_json:
        log.debug("structured_extraction: app:extraction_schema is set but no temp:document_blocks found; skipping")
        return None

    doc_id = callback_context.state.get("temp:document_id", "unknown")
    log.info("structured_extraction: running extraction for doc %s with schema", doc_id)

    try:
        result_json = await _run_extraction(blocks_json, schema)
    except Exception as exc:
        log.warning("structured_extraction: extraction failed for doc %s: %s", doc_id, exc)
        callback_context.state["temp:extraction_result"] = json.dumps(
            {"error": f"Extraction failed: {exc}", "doc_id": doc_id}
        )
        return None

    if len(result_json) > _LARGE_OUTPUT_THRESHOLD:
        artifact_id = f"extraction_{doc_id}"
        try:
            part = genai_types.Part.from_text(result_json)
            await callback_context.save_artifact(filename=artifact_id, artifact=part)
            callback_context.state["temp:extraction_result"] = json.dumps(
                {"artifact_id": artifact_id, "doc_id": doc_id, "truncated": True}
            )
            log.info("structured_extraction: large result saved as artifact %s", artifact_id)
            return None
        except Exception as exc:
            log.warning("structured_extraction: artifact save failed: %s", exc)

    callback_context.state["temp:extraction_result"] = result_json
    return None


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
    else:
        schema_str = json.dumps(schema, indent=2)

    prompt = (
        "You are a precise data extraction assistant. "
        "Extract structured data from the document blocks below according to the JSON schema provided.\n"
        "Return ONLY valid JSON that matches the schema exactly. "
        "Do not add explanation or markdown fencing.\n\n"
        f"JSON Schema:\n{schema_str}\n\n"
        f"Document blocks (JSON):\n{blocks_json}"
    )

    client = genai.Client(vertexai=True)
    response = await client.aio.models.generate_content(
        model=_EXTRACTION_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    text = response.text or ""
    if not text:
        raise ValueError("Gemini returned empty extraction response")

    json.loads(text)
    return text
