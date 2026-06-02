"""Pre-defined JSON schemas for structured data extraction.

Ported from v5 tools/schemas/__init__.py — JSON Schema format, not Pydantic.
These dicts are passed directly to structured_extraction_callback via
app:extraction_schema session state.
"""

from __future__ import annotations

import json
from typing import Any

SCHEMAS: dict[str, dict[str, Any]] = {
    "summary": {
        "type": "object",
        "description": "A structured summary of the document or response",
        "properties": {
            "main_topic": {"type": "string", "description": "The primary topic or subject discussed"},
            "summary": {"type": "string", "description": "A concise 1-2 sentence summary"},
            "key_points": {
                "type": "array",
                "description": "List of the most important points",
                "items": {"type": "string"},
            },
            "confidence_score": {
                "type": "number",
                "description": "Confidence level 0.0-1.0",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "propertyOrdering": ["main_topic", "summary", "key_points", "confidence_score"],
        "required": ["summary", "key_points"],
    },
    "entities": {
        "type": "object",
        "description": "Extract named entities and concepts",
        "properties": {
            "people": {"type": "array", "items": {"type": "string"}},
            "organizations": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "dates_times": {"type": "array", "items": {"type": "string"}},
            "concepts": {"type": "array", "items": {"type": "string"}},
            "urls": {"type": "array", "items": {"type": "string"}},
        },
        "propertyOrdering": ["people", "organizations", "locations", "dates_times", "concepts", "urls"],
    },
    "action_items": {
        "type": "object",
        "description": "Extract actionable tasks and next steps",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        "category": {"type": "string"},
                        "deadline": {"type": "string"},
                    },
                    "required": ["description", "priority"],
                },
            },
            "follow_up_questions": {"type": "array", "items": {"type": "string"}},
            "decisions_needed": {"type": "array", "items": {"type": "string"}},
        },
        "propertyOrdering": ["tasks", "follow_up_questions", "decisions_needed"],
    },
    "invoice": {
        "type": "object",
        "description": "Extract structured data from an invoice",
        "properties": {
            "invoice_number": {"type": "string"},
            "invoice_date": {"type": "string"},
            "vendor_name": {"type": "string"},
            "customer_name": {"type": "string"},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": {"type": "string"},
                        "total_price": {"type": "string"},
                    },
                    "required": ["description"],
                },
            },
            "subtotal": {"type": "string"},
            "tax_amount": {"type": "string"},
            "total_amount": {"type": "string"},
            "currency": {"type": "string"},
            "due_date": {"type": "string"},
        },
        "propertyOrdering": [
            "invoice_number",
            "invoice_date",
            "vendor_name",
            "customer_name",
            "line_items",
            "subtotal",
            "tax_amount",
            "total_amount",
            "currency",
            "due_date",
        ],
        "required": ["invoice_number", "vendor_name", "total_amount", "currency"],
    },
    "contract": {
        "type": "object",
        "description": "Extract key terms and obligations from a contract",
        "properties": {
            "contract_type": {"type": "string"},
            "parties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "effective_date": {"type": "string"},
            "expiry_date": {"type": "string"},
            "governing_law": {"type": "string"},
            "key_obligations": {"type": "array", "items": {"type": "string"}},
            "payment_terms": {"type": "string"},
            "termination_conditions": {"type": "array", "items": {"type": "string"}},
            "notices": {"type": "string"},
        },
        "propertyOrdering": [
            "contract_type",
            "parties",
            "effective_date",
            "expiry_date",
            "governing_law",
            "key_obligations",
            "payment_terms",
            "termination_conditions",
            "notices",
        ],
        "required": ["contract_type", "parties"],
    },
    # === AP-pipeline output contracts (SCHEMA-ENFORCE sprint) ===
    # Each specialist's output is constrained by these schemas:
    #   - invoice-extractor → ap_invoice
    #   - ap-validator      → ap_verdict
    #   - ap-poster         → ap_posting_record
    # additionalProperties: false strips prompt-injected fields before they
    # reach downstream consumers (defence in depth against output expansion
    # attacks). No oneOf/anyOf — Gemini's constrained-decoding subset rejects
    # those; conditional shapes use a flat enum discriminator with optional
    # fields, enforced server-side via Draft 2020-12 if/then/else in the
    # structured_extraction_callback validation pass.
    "ap_invoice": {
        "type": "object",
        "description": "AP invoice extraction output (invoice-extractor specialist)",
        "properties": {
            "vendor_name": {"type": "string"},
            "vendor_id": {"type": "string"},
            "invoice_number": {"type": "string"},
            "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
            "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            "po_reference": {"type": "string"},
            "currency": {"type": "string", "description": "ISO 4217 code, eg. EUR"},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": {"type": "number"},
                        "amount": {"type": "number"},
                    },
                    "required": ["description", "amount"],
                    "additionalProperties": False,
                },
            },
            "subtotal": {"type": "number"},
            "tax": {"type": "number"},
            "total": {"type": "number"},
            "confidence_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Low-confidence fields for multimodal extractions (PDFs/scans)",
            },
            "arithmetic_warning": {
                "type": "string",
                "description": "Set when sum(line_items.amount)+tax != total",
            },
        },
        "required": ["vendor_name", "invoice_number", "total", "currency"],
        "additionalProperties": False,
    },
    "ap_verdict": {
        "type": "object",
        "description": "AP validator verdict (ap-validator specialist)",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["pass", "needs_review"],
            },
            "reasons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "check": {
                            "type": "string",
                            "enum": ["vendor", "po", "duplicate", "policy", "tax"],
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["pass", "info", "warning", "fail"],
                        },
                        "detail": {"type": "string"},
                        "citation": {
                            "type": "string",
                            "description": "Source datastore reference (eg. vendor-V-1042)",
                        },
                    },
                    "required": ["check", "severity", "detail"],
                    "additionalProperties": False,
                },
            },
            "citations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All datastore document ids consulted",
            },
        },
        "required": ["verdict", "reasons"],
        "additionalProperties": False,
    },
    "ap_posting_record": {
        "type": "object",
        "description": (
            "AP poster outcome (ap-poster specialist). Flat action enum + "
            "optional fields rather than oneOf — Gemini's constrained-decoding "
            "subset doesn't support oneOf. The if/then/else block below is "
            "enforced server-side via Draft 2020-12 in the extraction "
            "validation pass (not in Gemini's decode constraint)."
        ),
        "properties": {
            "action": {
                "type": "string",
                "enum": ["post", "escalate"],
            },
            "invoice": {
                "type": "object",
                "description": "The validated invoice fields being acted on",
            },
            "posting_id": {
                "type": "string",
                "description": "ERP posting reference, present when action=post",
            },
            "ledger_account": {
                "type": "string",
                "description": "GL code the posting was applied to",
            },
            "escalation_reason": {
                "type": "string",
                "description": "Human-readable rationale, present when action=escalate",
            },
            "escalation_assignee": {
                "type": "string",
                "description": "Role/team to review (eg. Finance Manager)",
            },
            "audit_citations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Datastore ids forwarded from the validator",
            },
        },
        "required": ["action", "invoice"],
        "additionalProperties": False,
        # Conditional enforcement — server-side jsonschema (not Gemini decode):
        # action="post" requires posting_id; action="escalate" requires
        # escalation_reason. Draft 2020-12 if/then/else.
        "if": {"properties": {"action": {"const": "post"}}},
        "then": {"required": ["action", "invoice", "posting_id"]},
        "else": {"required": ["action", "invoice", "escalation_reason"]},
    },
    "meeting_minutes": {
        "type": "object",
        "description": "Extract structured data from meeting minutes",
        "properties": {
            "meeting_date": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "agenda_items": {"type": "array", "items": {"type": "string"}},
            "decisions": {"type": "array", "items": {"type": "string"}},
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "owner": {"type": "string"},
                        "due_date": {"type": "string"},
                    },
                    "required": ["task"],
                },
            },
            "next_meeting": {"type": "string"},
        },
        "propertyOrdering": [
            "meeting_date",
            "attendees",
            "agenda_items",
            "decisions",
            "action_items",
            "next_meeting",
        ],
        "required": ["meeting_date", "decisions"],
    },
}


def get_schema(name: str) -> dict[str, Any]:
    """Return a pre-defined schema by name.

    Raises:
        ValueError: If the name is not in SCHEMAS.
    """
    if name not in SCHEMAS:
        available = ", ".join(sorted(SCHEMAS))
        raise ValueError(f"Unknown schema {name!r}. Available: {available}")
    return SCHEMAS[name]


def list_schemas() -> list[str]:
    """Return all available pre-defined schema names."""
    return sorted(SCHEMAS)


def load_schema_from_file(file_path: str) -> dict[str, Any]:
    """Load a JSON Schema from a file."""
    with open(file_path) as f:
        return json.load(f)


def resolve_schema_ref(value: str | dict | None) -> dict | None:
    """Resolve a SkillMetadata.extraction_schema value into a JSON Schema dict.

    SKILL.md frontmatter authors can write either:
      extraction_schema: ap_invoice           # named reference
      extraction_schema: { type: object, ... } # inline schema

    Used at agent build time to seed app:extraction_schema in session state.

    Args:
        value: The raw extraction_schema field value from SkillMetadata.

    Returns:
        The resolved schema dict, or None when value is None.

    Raises:
        ValueError: When value is a string that does not match a registered
            schema name. The error message lists available names so the
            SKILL.md author can pick a valid one.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        if value not in SCHEMAS:
            available = ", ".join(sorted(SCHEMAS))
            raise ValueError(
                f"Unknown extraction_schema {value!r}. Available named schemas: {available}. "
                "Or supply an inline JSON Schema dict instead."
            )
        return SCHEMAS[value]
    raise ValueError(
        f"extraction_schema must be a string (named ref) or dict (inline schema), got {type(value).__name__}"
    )
