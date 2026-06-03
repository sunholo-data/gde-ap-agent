"""Function-as-schema emit tools for the AP pipeline specialists.

Why these exist
---------------

Gemini's API forbids combining ``tools`` with ``response_schema`` strict
mode in a single ``generate_content`` call. The historical workaround in
this template is a two-pass pattern: agent turn → after-agent callback
runs a SECOND Gemini call with ``response_schema`` set
(``backend/tools/structured_extraction.py``). It works but costs one
extra LLM round-trip per schema-bound specialist — for our 3-stage AP
pipeline, that's three extra calls per invoice (~10-15s of latency).

The cleaner pattern: declare the structured output as a FunctionTool
whose **typed parameters** mirror the JSON Schema. Gemini's
function-calling enforces those types — the model literally cannot
emit a call with the wrong arg types. One LLM call instead of two,
ADK-idiomatic, and the tool call event arrives at the frontend as a
clean TOOL_CALL_RESULT carrying the validated args (no JSON-sniffing
in the chat bubble).

Each ``emit_*`` tool below:

  1. Receives typed args matching its specialist's output schema.
  2. Writes the structured payload into session state under
     ``app:emitted:<skill>`` so downstream specialists (and the audit
     view) can read it without re-parsing the chat history.
  3. Returns a short confirmation string the LLM can use as the
     tool's response. The frontend treats the tool's *args* as the
     canonical output, not the return value.

When the LLM forgets to call the emit tool (rare with strong prompts,
but possible), the existing ``structured_extraction_callback``
after-agent fallback in ``structured_extraction.py`` still fires —
belt-and-braces. The fallback no-ops when ``app:emitted:<skill>`` is
already set, so we don't double-extract.

See docs/learnings/template-protocols-friction.md for the workshop
write-up.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.tools import FunctionTool, ToolContext

logger = logging.getLogger(__name__)

# Session-state keys downstream specialists + audit view read.
STATE_EMITTED_INVOICE = "app:emitted:invoice"
STATE_EMITTED_VERDICT = "app:emitted:verdict"
STATE_EMITTED_POSTING = "app:emitted:posting"


async def emit_invoice_extraction(
    vendor_name: str,
    invoice_number: str,
    currency: str,
    total: float,
    invoice_date: str = "",
    due_date: str = "",
    po_reference: str = "",
    vendor_id: str = "",
    subtotal: float = 0.0,
    tax: float = 0.0,
    line_items_json: str = "[]",
    confidence_notes: str = "",
    arithmetic_warning: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Emit the extracted invoice in the canonical `ap_invoice` schema.

    Call this **exactly once** at the end of your turn, after reading the
    parsed document blocks. The args ARE the structured output — Gemini's
    function-calling enforces their types, so emitting them this way is
    schema-validated by construction. There is no separate JSON return.

    Args:
        vendor_name: Vendor / supplier name as printed on the invoice.
        invoice_number: Vendor's invoice number / reference (eg. ``INV-2026-042``).
        currency: ISO 4217 currency code (eg. ``EUR``, ``USD``).
        total: Invoice grand total — numeric, NOT a formatted string.
        invoice_date: Date on the invoice in ``YYYY-MM-DD`` form.
        due_date: Payment due date in ``YYYY-MM-DD`` form.
        po_reference: Purchase-order reference if the invoice cites one.
        vendor_id: Internal vendor master id when the invoice carries one.
        subtotal: Pre-tax total — numeric.
        tax: Tax amount — numeric.
        line_items_json: JSON-encoded array of line items
            (``[{"description": "...", "quantity": 1, "unit_price": 0, "amount": 0}, ...]``).
            Passed as a string because nested-object args aren't reliably
            enforced by Gemini function-calling — the tool parses + validates
            internally.
        confidence_notes: Comma-separated list of low-confidence fields when
            extraction was multimodal (PDFs / scans).
        arithmetic_warning: Non-empty when ``sum(line_items.amount) + tax !=
            total``.
        tool_context: ADK ToolContext (injected; do not pass).

    Returns:
        A short confirmation string the model includes in its turn output.
        The structured payload lives in session state under
        ``app:emitted:invoice`` for downstream specialists.
    """
    try:
        line_items = json.loads(line_items_json) if line_items_json else []
        if not isinstance(line_items, list):
            line_items = []
    except json.JSONDecodeError as exc:
        logger.warning("emit_invoice_extraction: bad line_items_json (%s) — storing empty list", exc)
        line_items = []

    payload: dict[str, Any] = {
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "currency": currency,
        "total": total,
    }
    # Only include optional fields when populated so downstream agents
    # see ``key in payload`` semantics consistent with the JSON Schema.
    if invoice_date:
        payload["invoice_date"] = invoice_date
    if due_date:
        payload["due_date"] = due_date
    if po_reference:
        payload["po_reference"] = po_reference
    if vendor_id:
        payload["vendor_id"] = vendor_id
    if subtotal:
        payload["subtotal"] = subtotal
    if tax:
        payload["tax"] = tax
    if line_items:
        payload["line_items"] = line_items
    if confidence_notes:
        payload["confidence_notes"] = [s.strip() for s in confidence_notes.split(",") if s.strip()]
    if arithmetic_warning:
        payload["arithmetic_warning"] = arithmetic_warning

    if tool_context is not None and getattr(tool_context, "state", None) is not None:
        tool_context.state[STATE_EMITTED_INVOICE] = payload
    return f"Emitted ap_invoice for {vendor_name} / {invoice_number} (total {currency} {total})."


async def emit_ap_verdict(
    verdict: str,
    reasons_json: str = "[]",
    citations_csv: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Emit the validator's verdict in the canonical `ap_verdict` schema.

    Call this **exactly once** at the end of your turn after running the
    checks (vendor lookup, duplicate check, PO match, policy, tax). Pass
    the verdict + reasons as typed args; the frontend renders the args
    as an A2UI Card.

    Args:
        verdict: One of ``"pass"`` or ``"needs_review"``.
        reasons_json: JSON-encoded array of finding objects:
            ``[{"check": "vendor"|"po"|"duplicate"|"policy"|"tax",
                "severity": "pass"|"info"|"warning"|"fail",
                "detail": "...",
                "citation": "..."}, ...]``.
            String-encoded because nested-object args aren't reliably
            enforced by Gemini function-calling.
        citations_csv: Comma-separated datastore document ids consulted
            during the run (vendor master entries, PO docs, policy docs).
        tool_context: ADK ToolContext (injected; do not pass).

    Returns:
        Confirmation string. The structured payload lives at
        ``app:emitted:verdict`` for the poster + audit view.
    """
    if verdict not in {"pass", "needs_review"}:
        # Soft-clamp to needs_review on bad input so downstream agents
        # never see an unknown verdict value.
        logger.warning("emit_ap_verdict: unexpected verdict %r — coercing to 'needs_review'", verdict)
        verdict = "needs_review"

    try:
        reasons = json.loads(reasons_json) if reasons_json else []
        if not isinstance(reasons, list):
            reasons = []
    except json.JSONDecodeError as exc:
        logger.warning("emit_ap_verdict: bad reasons_json (%s) — storing empty list", exc)
        reasons = []

    payload: dict[str, Any] = {
        "verdict": verdict,
        "reasons": reasons,
    }
    if citations_csv:
        payload["citations"] = [s.strip() for s in citations_csv.split(",") if s.strip()]

    if tool_context is not None and getattr(tool_context, "state", None) is not None:
        tool_context.state[STATE_EMITTED_VERDICT] = payload
    return f"Emitted ap_verdict verdict={verdict} ({len(reasons)} reasons)."


async def emit_posting_record(
    action: str,
    invoice_json: str,
    posting_id: str = "",
    ledger_account: str = "",
    escalation_reason: str = "",
    escalation_assignee: str = "",
    audit_citations_csv: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Emit the poster's outcome in the canonical `ap_posting_record` schema.

    Call this **exactly once** at the end of your turn AFTER the MCP
    post_to_ledger or route_to_approval call returns. Pass the action
    branch + the invoice that was acted on + the MCP-returned ids.

    Args:
        action: One of ``"post"`` (verdict=pass → ledger) or
            ``"escalate"`` (verdict=needs_review → approval queue).
        invoice_json: JSON-encoded invoice object (the validated invoice
            fields from upstream — pass exactly what you received via
            session state). String-encoded for the same reason as the
            other emit tools' nested args.
        posting_id: Required when ``action="post"``. The ERP posting id
            returned by the ``post_to_ledger`` MCP tool.
        ledger_account: GL code the posting was applied to.
        escalation_reason: Required when ``action="escalate"``. Human
            rationale for routing rather than posting.
        escalation_assignee: Role / team to review (eg. ``"Finance Manager"``).
        audit_citations_csv: Comma-separated datastore ids forwarded
            from the validator.
        tool_context: ADK ToolContext (injected; do not pass).

    Returns:
        Confirmation string. The structured payload lives at
        ``app:emitted:posting`` for the audit view.
    """
    if action not in {"post", "escalate"}:
        logger.warning("emit_posting_record: unexpected action %r — coercing to 'escalate'", action)
        action = "escalate"

    try:
        invoice = json.loads(invoice_json) if invoice_json else {}
        if not isinstance(invoice, dict):
            invoice = {}
    except json.JSONDecodeError as exc:
        logger.warning("emit_posting_record: bad invoice_json (%s) — storing empty dict", exc)
        invoice = {}

    payload: dict[str, Any] = {
        "action": action,
        "invoice": invoice,
    }
    if action == "post":
        if not posting_id:
            logger.warning("emit_posting_record: action=post but posting_id is empty — schema violation")
        payload["posting_id"] = posting_id
        if ledger_account:
            payload["ledger_account"] = ledger_account
    else:
        if not escalation_reason:
            logger.warning("emit_posting_record: action=escalate but escalation_reason is empty — schema violation")
        payload["escalation_reason"] = escalation_reason
        if escalation_assignee:
            payload["escalation_assignee"] = escalation_assignee
    if audit_citations_csv:
        payload["audit_citations"] = [s.strip() for s in audit_citations_csv.split(",") if s.strip()]

    if tool_context is not None and getattr(tool_context, "state", None) is not None:
        tool_context.state[STATE_EMITTED_POSTING] = payload
    return f"Emitted ap_posting_record action={action} posting_id={posting_id or 'n/a'}."


# Convenience for the tool registry.
EMIT_TOOLS: dict[str, FunctionTool] = {
    "emit_invoice_extraction": FunctionTool(emit_invoice_extraction),
    "emit_ap_verdict": FunctionTool(emit_ap_verdict),
    "emit_posting_record": FunctionTool(emit_posting_record),
}
