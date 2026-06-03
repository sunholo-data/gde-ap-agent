"""Unit tests for the simulated erp-posting MCP server.

WORKFLOW-PIPELINE M3. Exercises post_to_ledger + route_to_approval via
the FastMCP in-process call_tool — confirms the action returns a
posting_id/ticket_id the ap-poster can carry into the Invoice Review
Card.
"""

from __future__ import annotations

import json
import re

import pytest

from protocols.mcp_servers.erp_posting import erp_posting_mcp


def _extract_dict(result) -> dict:
    """FastMCP serialises dict returns — tuple or TextContent JSON."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        return result[1]
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, list):
        for block in result:
            txt = getattr(block, "text", None)
            if isinstance(txt, str):
                try:
                    parsed = json.loads(txt)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        raise AssertionError(f"no dict-shaped content block in {result!r}")
    if isinstance(result, dict):
        return result
    raise AssertionError(f"unrecognised call_tool result shape: {result!r}")


_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_POSTING_ID_RE = re.compile(r"^POST-[0-9A-F]{8}$")
_TICKET_ID_RE = re.compile(r"^APPR-[0-9A-F]{8}$")


_INVOICE = {
    "vendor_name": "Acme GmbH",
    "invoice_number": "INV-2026-042",
    "total": 6800.00,
    "currency": "EUR",
    "line_items": [{"description": "Services", "quantity": 1, "unit_price": 6800.00, "amount": 6800.00}],
}


@pytest.mark.asyncio
async def test_post_to_ledger_returns_posting_id_and_iso_timestamp():
    """A successful post must return a fresh POST-... id and ISO8601 timestamp
    so the ap-poster can put them on the Invoice Review Card's action field."""
    result = await erp_posting_mcp.call_tool(
        "post_to_ledger",
        {"invoice": _INVOICE, "gl_code": "6000-IT-SVC", "posting_period": "2026-06"},
    )
    data = _extract_dict(result)
    assert _POSTING_ID_RE.match(data["posting_id"]), f"bad posting_id: {data['posting_id']!r}"
    assert _ISO8601_RE.match(data["posted_at"]), f"bad posted_at: {data['posted_at']!r}"
    assert data["status"] == "POSTED"
    assert data["gl_account"] == "6000-IT-SVC"
    assert data["amount"] == 6800.00
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_post_to_ledger_defaults_gl_account_to_pending_when_blank():
    """If the poster can't derive a GL code yet, the action still records
    a posting (a real ERP would 400 — this is the simulated permissive path
    for demo)."""
    result = await erp_posting_mcp.call_tool(
        "post_to_ledger",
        {"invoice": _INVOICE, "gl_code": "", "posting_period": "2026-06"},
    )
    data = _extract_dict(result)
    assert data["gl_account"] == "PENDING"


@pytest.mark.asyncio
async def test_route_to_approval_emits_ticket_with_sla():
    """A needs_review invoice goes to the finance queue with a 24h SLA
    and an APPR-... ticket id."""
    reasons = [
        "vendor KYC pending — Umbrella Supplies",
        "PO match: total exceeds open PO by 12%",
    ]
    result = await erp_posting_mcp.call_tool(
        "route_to_approval",
        {"invoice": _INVOICE, "reasons": reasons},
    )
    data = _extract_dict(result)
    assert _TICKET_ID_RE.match(data["ticket_id"]), f"bad ticket_id: {data['ticket_id']!r}"
    assert data["queue"] == "finance"
    assert data["sla_hours"] == 24
    assert _ISO8601_RE.match(data["opened_at"])
    assert data["reasons"] == reasons
    assert data["vendor"] == "Acme GmbH"
    assert data["total"] == 6800.00


@pytest.mark.asyncio
async def test_post_and_route_emit_different_id_prefixes():
    """The two ID prefixes (POST- vs APPR-) keep the audit trail
    unambiguous on the card — a glance distinguishes posted from routed."""
    posted = _extract_dict(
        await erp_posting_mcp.call_tool(
            "post_to_ledger",
            {"invoice": _INVOICE, "gl_code": "X", "posting_period": "2026-06"},
        )
    )
    routed = _extract_dict(
        await erp_posting_mcp.call_tool(
            "route_to_approval",
            {"invoice": _INVOICE, "reasons": ["test"]},
        )
    )
    assert posted["posting_id"].startswith("POST-")
    assert routed["ticket_id"].startswith("APPR-")
    assert posted["posting_id"] != routed["ticket_id"]
