"""Generate the demo vendor-master JSONL for Vertex AI Search import.

Produces 15 documents (5 vendors + 3 POs + 3 prior invoices + 3 policies +
1 catch-all) in the Discovery Engine `document` data schema:

    { id, structData, content: { mimeType, rawBytes (base64) } }

Run:
    python3 infrastructure/demo-vendor-master/generate.py

Output:
    infrastructure/demo-vendor-master/vendor-master.jsonl

The loader script (scripts/load-vendor-master.sh) uploads this file to
GCS and calls dataStores/<id>/branches/0/documents:import with
gcsSource.dataSchema=document.

Demo realism: vendor + PO IDs cross-reference each other and the
example invoices under infrastructure/demo-invoices/ so validator
runs against the demo invoices return grounded results (eg. the
acme-gmbh-invoice-2026-042.docx invoice cites PO-2026-0189 from this
master).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "vendor-master.jsonl"

DOCS: list[tuple[str, dict, str]] = [
    # --- Vendors ---
    (
        "vendor-V-1042",
        {
            "type": "vendor",
            "vendor_id": "V-1042",
            "vendor_name": "Acme GmbH",
            "country": "DE",
            "approved": True,
            "category": "Cloud Services",
            "spend_limit_eur": 50000,
            "bank_iban": "DE89 3704 0044 0532 0130 00",
            "vat_id": "DE123456789",
            "preferred_supplier": True,
        },
        "Vendor master record. Vendor ID: V-1042. Name: Acme GmbH. Country: Germany (DE). "
        "Approved supplier: YES. Category: Cloud Services. Spend limit per invoice: EUR 50,000. "
        "Bank: Deutsche Bank, IBAN DE89 3704 0044 0532 0130 00. VAT registration: DE123456789. "
        "Address: Friedrichstrasse 123, 10117 Berlin, Germany. Status: active. "
        "Preferred supplier programme: enrolled. Payment terms: NET 30. Currency: EUR. "
        "Contact: accounting@acme-gmbh.example.",
    ),
    (
        "vendor-V-2014",
        {
            "type": "vendor",
            "vendor_id": "V-2014",
            "vendor_name": "TechCorp Ltd",
            "country": "GB",
            "approved": True,
            "category": "Software Licences",
            "spend_limit_eur": 25000,
            "bank_iban": "GB29 NWBK 6016 1331 9268 19",
            "vat_id": "GB987654321",
        },
        "Vendor master record. Vendor ID: V-2014. Name: TechCorp Ltd. Country: United Kingdom (GB). "
        "Approved supplier: YES. Category: Software Licences. Spend limit per invoice: EUR 25,000. "
        "Bank: NatWest, IBAN GB29 NWBK 6016 1331 9268 19. VAT registration: GB987654321. "
        "Address: 22 Aldwych, London WC2B 4DR, UK. Status: active. Payment terms: NET 45. "
        "Currency: GBP. Contact: ap@techcorp.example.",
    ),
    (
        "vendor-V-3077",
        {
            "type": "vendor",
            "vendor_id": "V-3077",
            "vendor_name": "Nordic Parts AB",
            "country": "SE",
            "approved": True,
            "category": "Manufacturing Parts",
            "spend_limit_eur": 15000,
            "bank_iban": "SE45 5000 0000 0583 9825 7466",
            "vat_id": "SE556677889012",
        },
        "Vendor master record. Vendor ID: V-3077. Name: Nordic Parts AB. Country: Sweden (SE). "
        "Approved supplier: YES. Category: Manufacturing Parts. Spend limit per invoice: EUR 15,000. "
        "Bank: SEB, IBAN SE45 5000 0000 0583 9825 7466. VAT registration: SE556677889012. "
        "Address: Sveavaegen 44, 111 34 Stockholm, Sweden. Status: active. Payment terms: NET 30. "
        "Currency: EUR. Contact: billing@nordic-parts.example.",
    ),
    (
        "vendor-V-4090",
        {
            "type": "vendor",
            "vendor_id": "V-4090",
            "vendor_name": "Apex Consulting",
            "country": "FR",
            "approved": True,
            "category": "Professional Services",
            "spend_limit_eur": 75000,
            "bank_iban": "FR14 2004 1010 0505 0001 3M02 606",
            "vat_id": "FRAB123456789",
        },
        "Vendor master record. Vendor ID: V-4090. Name: Apex Consulting. Country: France (FR). "
        "Approved supplier: YES. Category: Professional Services. Spend limit per invoice: EUR 75,000. "
        "Bank: BNP Paribas, IBAN FR14 2004 1010 0505 0001 3M02 606. VAT registration: FRAB123456789. "
        "Address: 75 Avenue des Champs-Elysees, 75008 Paris, France. Status: active. "
        "Payment terms: NET 60. Currency: EUR. Contact: invoicing@apex-consulting.example.",
    ),
    (
        "vendor-V-9001",
        {
            "type": "vendor",
            "vendor_id": "V-9001",
            "vendor_name": "BlockedCo S.A.",
            "country": "ES",
            "approved": False,
            "category": "Unknown",
            "spend_limit_eur": 0,
            "block_reason": "Failed compliance check 2026-04",
        },
        "Vendor master record. Vendor ID: V-9001. Name: BlockedCo S.A. Country: Spain (ES). "
        "Approved supplier: NO. Block reason: Failed compliance check in April 2026. "
        "Do not pay invoices from this vendor without Finance Director sign-off and a "
        "re-onboarding review. Status: blocked. Spend limit: 0.",
    ),
    # --- Open POs ---
    (
        "po-PO-2026-0189",
        {
            "type": "po",
            "po_number": "PO-2026-0189",
            "vendor_id": "V-1042",
            "vendor_name": "Acme GmbH",
            "currency": "EUR",
            "total_amount": 9000,
            "status": "open",
        },
        "Purchase Order PO-2026-0189. Vendor: Acme GmbH (V-1042). Status: open. "
        "Total: EUR 9,000.00. Issued: 2026-05-15. Expected delivery: 2026-06-15. "
        "Line items: 1 x Cloud Services Subscription May 2026 at EUR 9,000.00. "
        "Approver: J. Doe (Engineering Manager). GL code: 5200-OPEX-CLOUD.",
    ),
    (
        "po-PO-2026-0204",
        {
            "type": "po",
            "po_number": "PO-2026-0204",
            "vendor_id": "V-2014",
            "vendor_name": "TechCorp Ltd",
            "currency": "GBP",
            "total_amount": 18500,
            "status": "open",
        },
        "Purchase Order PO-2026-0204. Vendor: TechCorp Ltd (V-2014). Status: open. "
        "Total: GBP 18,500.00. Issued: 2026-05-22. Expected delivery: 2026-06-22. "
        "Line items: 3 x Software Licences (Annual). Approver: M. Smith (CTO). "
        "GL code: 5100-SW-LICENCE.",
    ),
    (
        "po-PO-2026-0311",
        {
            "type": "po",
            "po_number": "PO-2026-0311",
            "vendor_id": "V-4090",
            "vendor_name": "Apex Consulting",
            "currency": "EUR",
            "total_amount": 45000,
            "status": "open",
        },
        "Purchase Order PO-2026-0311. Vendor: Apex Consulting (V-4090). Status: open. "
        "Total: EUR 45,000.00. Issued: 2026-04-01. Expected delivery: 2026-09-30. "
        "Line items: 1 x Strategy Engagement Q2-Q3 2026. Approver: A. Stevens (CEO). "
        "GL code: 5400-PROF-SVCS.",
    ),
    # --- Prior invoices (for duplicate detection) ---
    (
        "prior-invoice-INV-2025-119",
        {
            "type": "prior_invoice",
            "invoice_number": "INV-2025-119",
            "vendor_id": "V-1042",
            "vendor_name": "Acme GmbH",
            "currency": "EUR",
            "total_amount": 8500,
            "posted_date": "2025-11-15",
            "status": "posted",
        },
        "Prior invoice INV-2025-119. Vendor: Acme GmbH (V-1042). Amount: EUR 8,500.00. "
        "Invoice date: 2025-11-01. Posted to AP ledger: 2025-11-15. Status: posted. "
        "PO: PO-2025-0890 (closed). This is a DIFFERENT invoice number than INV-2026-042 "
        "and was paid five months earlier.",
    ),
    (
        "prior-invoice-INV-2025-187",
        {
            "type": "prior_invoice",
            "invoice_number": "INV-2025-187",
            "vendor_id": "V-1042",
            "vendor_name": "Acme GmbH",
            "currency": "EUR",
            "total_amount": 9000,
            "posted_date": "2026-02-20",
            "status": "posted",
        },
        "Prior invoice INV-2025-187. Vendor: Acme GmbH (V-1042). Amount: EUR 9,000.00 "
        "(same as PO-2026-0189 total). Invoice date: 2026-02-15. Posted to AP ledger: "
        "2026-02-20. Status: posted. This was a Q1 services invoice covering Cloud "
        "Services Subscription February 2026.",
    ),
    (
        "prior-invoice-INV-2026-018",
        {
            "type": "prior_invoice",
            "invoice_number": "INV-2026-018",
            "vendor_id": "V-2014",
            "vendor_name": "TechCorp Ltd",
            "currency": "GBP",
            "total_amount": 6150,
            "posted_date": "2026-03-10",
            "status": "posted",
        },
        "Prior invoice INV-2026-018. Vendor: TechCorp Ltd (V-2014). Amount: GBP 6,150.00. "
        "Invoice date: 2026-03-01. Posted to AP ledger: 2026-03-10. Status: posted. "
        "PO: PO-2026-0204. Software licence Q1 instalment.",
    ),
    # --- Approval policies ---
    (
        "policy-cloud-services",
        {
            "type": "policy",
            "category": "Cloud Services",
            "single_invoice_max_no_approval": 10000,
            "single_invoice_max_manager_approval": 25000,
            "above_threshold_approver": "CFO",
            "currency": "EUR",
        },
        "Approval policy: Cloud Services category. Single invoice up to EUR 10,000 "
        "auto-approved if vendor is in master, vendor is approved, and PO matches within "
        "EUR 100 tolerance. EUR 10,000 to EUR 25,000 requires Finance Manager approval "
        "AND a matching PO. Above EUR 25,000 requires CFO approval AND a matching PO AND "
        "a quarterly forecast adjustment note. Standard EU VAT rate: 19 percent for "
        "DE-registered vendors; 20 percent for FR-registered; 25 percent for SE-registered. "
        "UK VAT: 20 percent.",
    ),
    (
        "policy-software-licences",
        {
            "type": "policy",
            "category": "Software Licences",
            "single_invoice_max_no_approval": 5000,
            "single_invoice_max_manager_approval": 30000,
            "above_threshold_approver": "CTO+CFO",
            "currency": "EUR",
        },
        "Approval policy: Software Licences category. Single invoice up to EUR 5,000 "
        "auto-approved if vendor is in master and vendor is approved. EUR 5,000 to "
        "EUR 30,000 requires manager approval AND a PO. Above EUR 30,000 requires CTO "
        "and CFO joint approval. Annual licences must be tied to a current PO.",
    ),
    (
        "policy-duplicate-detection",
        {"type": "policy", "category": "Duplicate Detection"},
        "Duplicate detection policy. Two invoices are considered DUPLICATES if they share "
        "the same vendor_id AND the same invoice_number, OR if they share the same "
        "vendor_id, the same total amount, AND invoice_date within 7 days. Flag any "
        "candidate duplicates as needs_review with citation to the prior invoice. Vendors "
        "are allowed to re-bill the same amount in different months for recurring services "
        "(e.g., Cloud Services Subscription is monthly EUR 9,000 from Acme GmbH); only "
        "flag as duplicate when the dates collide within the 7-day window.",
    ),
]


def main() -> None:
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for doc_id, struct, text in DOCS:
            doc = {
                "id": doc_id,
                "structData": struct,
                "content": {
                    "mimeType": "text/plain",
                    "rawBytes": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                },
            }
            f.write(json.dumps(doc, separators=(",", ":")) + "\n")
    print(f"Wrote {len(DOCS)} documents to {OUT_PATH}")


if __name__ == "__main__":
    main()
