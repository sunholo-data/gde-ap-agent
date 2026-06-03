"""Simulated vendor-master MCP server.

Exposes:
  - lookup_vendor(name) → {found, vendor_id, country, payment_terms,
                          kyc_status, currency}
  - check_duplicate(invoice_number, vendor_id) → {duplicate, posted_at,
                                                  posting_id}

The synthetic vendor table covers the demo invoices (Acme GmbH,
Globex, ACME Software Solutions etc.) so the validator's grounded
checks return believable results during the Track 3 submission demo.

This server runs in-process at /mcp/vendor-master alongside the main
/mcp server. Same trust boundary, same Cloud Run service edge — no new
data egress. See WORKFLOW-PIPELINE M3 in
docs/design/forks/gde-ap-agent/multi-agent-workflow-pipeline.md.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger(__name__)

vendor_master_mcp = FastMCP(
    "vendor-master",
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# Synthetic vendor master. Keys are normalised (lowercased, stripped) so
# small input variations from the LLM's extraction still match.
_VENDORS: dict[str, dict] = {
    "acme gmbh": {
        "vendor_id": "V-1042",
        "country": "DE",
        "payment_terms": "NET30",
        "kyc_status": "verified",
        "currency": "EUR",
    },
    "acme software solutions": {
        "vendor_id": "V-1042-US",
        "country": "US",
        "payment_terms": "NET45",
        "kyc_status": "verified",
        "currency": "USD",
    },
    "globex industries": {
        "vendor_id": "V-2188",
        "country": "GB",
        "payment_terms": "NET30",
        "kyc_status": "verified",
        "currency": "GBP",
    },
    "initech consulting": {
        "vendor_id": "V-3301",
        "country": "US",
        "payment_terms": "NET15",
        "kyc_status": "verified",
        "currency": "USD",
    },
    "umbrella supplies": {
        "vendor_id": "V-4499",
        "country": "FR",
        "payment_terms": "NET60",
        # Unverified KYC — used to demo the "needs_review" path.
        "kyc_status": "pending",
        "currency": "EUR",
    },
    "cyberdyne systems": {
        "vendor_id": "V-5512",
        "country": "JP",
        "payment_terms": "NET30",
        "kyc_status": "verified",
        "currency": "JPY",
    },
}


# Synthetic posting history — used to flag duplicate-payment risk. A
# real ERP would query a postings table here; this stub returns a few
# fixed dupes so the validator's check_duplicate call is visibly
# grounded during the demo.
_POSTING_HISTORY: dict[tuple[str, str], dict] = {
    # (invoice_number, vendor_id): posting record
    ("INV-2026-001", "V-1042"): {
        "posted_at": "2026-05-12T09:42:11Z",
        "posting_id": "POST-A1B2C3",
    },
    ("INV-2026-017", "V-2188"): {
        "posted_at": "2026-05-28T14:08:55Z",
        "posting_id": "POST-D4E5F6",
    },
}


def _normalise(name: str) -> str:
    return (name or "").strip().lower()


@vendor_master_mcp.tool()
def lookup_vendor(name: str) -> dict:
    """Look up a vendor by name in the master file.

    Args:
        name: Vendor name as it appears on the invoice (case-insensitive,
            whitespace-tolerant).

    Returns:
        On match: {found: true, vendor_id, country, payment_terms,
                   kyc_status, currency}.
        On miss:  {found: false, name: <normalised input>}.

    The validator should treat `found=false` as `needs_review` with
    citation "vendor not in master", and `kyc_status != "verified"` as
    `needs_review` with citation "vendor KYC <status>".
    """
    key = _normalise(name)
    record = _VENDORS.get(key)
    if not record:
        logger.info("vendor_master.lookup_vendor: miss for name=%r", name)
        return {"found": False, "name": key}
    return {"found": True, **record}


@vendor_master_mcp.tool()
def check_duplicate(invoice_number: str, vendor_id: str) -> dict:
    """Check whether this invoice has already been posted.

    Args:
        invoice_number: The invoice number from the extracted invoice.
        vendor_id: The vendor's master file ID (from lookup_vendor).

    Returns:
        If a prior posting exists for the same (invoice_number, vendor_id):
            {duplicate: true, posted_at: ISO8601, posting_id: str}
        Otherwise: {duplicate: false}.

    The validator should treat `duplicate=true` as `needs_review` with
    the prior `posting_id` as citation.
    """
    key = ((invoice_number or "").strip(), (vendor_id or "").strip())
    record = _POSTING_HISTORY.get(key)
    if not record:
        return {"duplicate": False}
    return {"duplicate": True, **record}
