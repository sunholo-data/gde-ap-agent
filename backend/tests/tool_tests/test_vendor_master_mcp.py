"""Unit tests for the simulated vendor-master MCP server.

WORKFLOW-PIPELINE M3. Exercises the FastMCP instance directly via
call_tool() — the wire protocol is covered by mount-composition tests
on the parent FastAPI app. These confirm the synthetic vendor table
and posting history return the shapes the ap-validator skill expects.
"""

from __future__ import annotations

import json

import pytest

from protocols.mcp_servers.vendor_master import vendor_master_mcp


def _extract_dict(result) -> dict:
    """FastMCP serialises dict returns into a tuple (content, structured)
    or a single TextContent. Pull out the dict in a version-tolerant way.
    """
    # Newer FastMCP: tuple (content_blocks, structured_dict)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        return result[1]
    # Or a list of TextContent with a JSON-encoded dict body
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


@pytest.mark.asyncio
async def test_lookup_known_vendor_returns_master_data():
    """Acme GmbH is in the synthetic table — returns the full record."""
    result = await vendor_master_mcp.call_tool("lookup_vendor", {"name": "Acme GmbH"})
    data = _extract_dict(result)
    assert data["found"] is True
    assert data["vendor_id"] == "V-1042"
    assert data["country"] == "DE"
    assert data["kyc_status"] == "verified"
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_lookup_vendor_is_case_insensitive():
    """Real invoice names vary in capitalisation; the master must match."""
    result = await vendor_master_mcp.call_tool("lookup_vendor", {"name": "  acme gmbh  "})
    data = _extract_dict(result)
    assert data["found"] is True
    assert data["vendor_id"] == "V-1042"


@pytest.mark.asyncio
async def test_lookup_unknown_vendor_returns_not_found():
    """Vendor not in master → {found: False}. The validator treats this
    as needs_review with citation 'vendor not in master'."""
    result = await vendor_master_mcp.call_tool("lookup_vendor", {"name": "Definitely Fake Vendor LLC"})
    data = _extract_dict(result)
    assert data["found"] is False
    assert "vendor_id" not in data


@pytest.mark.asyncio
async def test_lookup_pending_kyc_vendor_surfaces_kyc_status():
    """Umbrella Supplies has kyc_status='pending' — used to demo the
    needs_review path even when the vendor is in the master."""
    result = await vendor_master_mcp.call_tool("lookup_vendor", {"name": "Umbrella Supplies"})
    data = _extract_dict(result)
    assert data["found"] is True
    assert data["kyc_status"] == "pending"


@pytest.mark.asyncio
async def test_check_duplicate_flags_known_invoice():
    """INV-2026-001 against vendor V-1042 was already posted — must surface
    the prior posting_id as the citation for the validator's duplicate check."""
    result = await vendor_master_mcp.call_tool(
        "check_duplicate",
        {"invoice_number": "INV-2026-001", "vendor_id": "V-1042"},
    )
    data = _extract_dict(result)
    assert data["duplicate"] is True
    assert data["posting_id"] == "POST-A1B2C3"
    assert data["posted_at"] == "2026-05-12T09:42:11Z"


@pytest.mark.asyncio
async def test_check_duplicate_returns_false_for_unseen_invoice():
    """A fresh invoice — duplicate=False, no posting fields."""
    result = await vendor_master_mcp.call_tool(
        "check_duplicate",
        {"invoice_number": "INV-2026-999", "vendor_id": "V-1042"},
    )
    data = _extract_dict(result)
    assert data["duplicate"] is False
    assert "posting_id" not in data
