"""Simulated erp-posting MCP server.

Exposes:
  - post_to_ledger(invoice, gl_code, posting_period) → {posting_id,
                                                       posted_at,
                                                       gl_account,
                                                       status}
  - route_to_approval(invoice, reasons) → {ticket_id, queue, sla_hours}

The ap-poster specialist calls one of these depending on the validator's
verdict (`pass` → post, `needs_review` → route). Synthetic outputs let
the demo show the final action surface (posting_id or ticket_id) on the
Invoice Review Card without needing a real ERP integration.

Mounted at /mcp/erp-posting alongside /mcp/vendor-master and the main
/mcp server. Same trust boundary, no new egress. See WORKFLOW-PIPELINE
M3 in docs/design/forks/gde-ap-agent/multi-agent-workflow-pipeline.md.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger(__name__)

erp_posting_mcp = FastMCP(
    "erp-posting",
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def _iso_now() -> str:
    """Return the current time as an ISO8601 UTC string."""
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _new_posting_id() -> str:
    """POST-<8 uppercase hex>. Short enough for the card, unique enough for demo."""
    return f"POST-{uuid.uuid4().hex[:8].upper()}"


def _new_ticket_id() -> str:
    """APPR-<8 uppercase hex>. Mirrors the posting_id shape for the approval queue."""
    return f"APPR-{uuid.uuid4().hex[:8].upper()}"


@erp_posting_mcp.tool()
def post_to_ledger(invoice: dict, gl_code: str, posting_period: str) -> dict:
    """Simulate posting an invoice to the AP general ledger.

    Args:
        invoice: The validated invoice payload (vendor, total, line_items, …).
        gl_code: The general-ledger account code chosen by the poster
            (e.g. "6000-IT-SVC"). May be "PENDING" if not derivable.
        posting_period: The accounting period (e.g. "2026-06").

    Returns:
        {posting_id, posted_at (ISO8601 UTC), gl_account, status: "POSTED",
         amount, currency} — the action's audit trail. The `posting_id`
        becomes the citation on the Invoice Review Card's action field.
    """
    posting_id = _new_posting_id()
    posted_at = _iso_now()
    amount = invoice.get("total") if isinstance(invoice, dict) else None
    currency = invoice.get("currency") if isinstance(invoice, dict) else None
    logger.info(
        "erp_posting.post_to_ledger: gl_code=%r period=%r → posting_id=%s",
        gl_code,
        posting_period,
        posting_id,
    )
    return {
        "posting_id": posting_id,
        "posted_at": posted_at,
        "gl_account": gl_code or "PENDING",
        "posting_period": posting_period,
        "status": "POSTED",
        "amount": amount,
        "currency": currency,
    }


@erp_posting_mcp.tool()
def route_to_approval(invoice: dict, reasons: list[str]) -> dict:
    """Route a `needs_review` invoice to a finance reviewer's approval queue.

    Args:
        invoice: The validated invoice payload.
        reasons: One human-readable line per failed validation check —
            comes verbatim from the validator's `ap_verdict.reasons[].detail`.

    Returns:
        {ticket_id, queue: "finance", sla_hours: 24, opened_at, reasons,
         vendor, total} — the ticket's audit trail. The `ticket_id`
        becomes the citation on the Invoice Review Card's action field.
    """
    ticket_id = _new_ticket_id()
    opened_at = _iso_now()
    vendor = invoice.get("vendor_name") or invoice.get("vendor") if isinstance(invoice, dict) else None
    total = invoice.get("total") if isinstance(invoice, dict) else None
    # Synthetic SLA: 24h for everything in the demo. A real router would
    # branch on severity / amount.
    sla_hours = 24
    logger.info(
        "erp_posting.route_to_approval: reasons=%d → ticket_id=%s",
        len(reasons or []),
        ticket_id,
    )
    return {
        "ticket_id": ticket_id,
        "queue": "finance",
        "sla_hours": sla_hours,
        "opened_at": opened_at,
        "reasons": list(reasons or []),
        "vendor": vendor,
        "total": total,
        "_handled_by": "erp-posting-mcp",
        "_received_at_epoch": time.time(),
    }
