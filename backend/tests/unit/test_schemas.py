"""Tests for tools/schemas — registry, resolver, AP-pipeline contracts.

SCHEMA-ENFORCE sprint: covers the new ap_invoice / ap_verdict /
ap_posting_record schemas plus the resolve_schema_ref helper used by
the before-agent extraction-schema setter.
"""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from tools.schemas import SCHEMAS, get_schema, list_schemas, resolve_schema_ref


class TestRegistry:
    def test_includes_ap_schemas(self):
        assert "ap_invoice" in SCHEMAS
        assert "ap_verdict" in SCHEMAS
        assert "ap_posting_record" in SCHEMAS

    def test_preserves_legacy_schemas(self):
        for legacy in ("summary", "entities", "action_items", "invoice", "contract", "meeting_minutes"):
            assert legacy in SCHEMAS, f"legacy schema {legacy!r} disappeared"

    def test_all_schemas_validate_against_metaschema(self):
        """Every registered schema must itself be a valid Draft 2020-12 JSON Schema."""
        for name, schema in SCHEMAS.items():
            Draft202012Validator.check_schema(schema)

    def test_get_schema_returns_dict(self):
        s = get_schema("ap_invoice")
        assert isinstance(s, dict)
        assert s["type"] == "object"

    def test_list_schemas_returns_sorted_names(self):
        names = list_schemas()
        assert names == sorted(names)
        assert "ap_invoice" in names


class TestApInvoiceSchema:
    """ap_invoice — invoice-extractor specialist output contract."""

    def setup_method(self):
        self.v = Draft202012Validator(SCHEMAS["ap_invoice"])

    def test_minimal_valid_invoice(self):
        payload = {
            "vendor_name": "Acme GmbH",
            "invoice_number": "INV-2026-042",
            "total": 9000.00,
            "currency": "EUR",
        }
        assert list(self.v.iter_errors(payload)) == []

    def test_full_invoice_with_line_items(self):
        payload = {
            "vendor_name": "Acme GmbH",
            "vendor_id": "V-1042",
            "invoice_number": "INV-2026-042",
            "invoice_date": "2026-06-01",
            "due_date": "2026-07-01",
            "po_reference": "PO-2026-0189",
            "currency": "EUR",
            "line_items": [
                {"description": "Cloud Services May 2026", "quantity": 1, "unit_price": 9000, "amount": 9000},
            ],
            "subtotal": 9000.0,
            "tax": 0.0,
            "total": 9000.0,
        }
        assert list(self.v.iter_errors(payload)) == []

    def test_missing_required_field_fails(self):
        # vendor_name is required
        payload = {"invoice_number": "INV-1", "total": 100, "currency": "EUR"}
        errors = list(self.v.iter_errors(payload))
        assert any("vendor_name" in str(e.message) for e in errors)

    def test_rejects_extra_top_level_field(self):
        """additionalProperties:false strips prompt-injected fields."""
        payload = {
            "vendor_name": "Acme",
            "invoice_number": "INV-1",
            "total": 100,
            "currency": "EUR",
            "exfiltrated_secret": "should_be_rejected",
        }
        errors = list(self.v.iter_errors(payload))
        assert any("exfiltrated_secret" in str(e.message) or "additional" in str(e.message).lower() for e in errors)


class TestApVerdictSchema:
    """ap_verdict — ap-validator specialist output contract."""

    def setup_method(self):
        self.v = Draft202012Validator(SCHEMAS["ap_verdict"])

    def test_pass_verdict(self):
        payload = {
            "verdict": "pass",
            "reasons": [
                {"check": "vendor", "severity": "pass", "detail": "V-1042 approved", "citation": "vendor-V-1042"},
                {"check": "po", "severity": "pass", "detail": "matches PO-2026-0189", "citation": "po-PO-2026-0189"},
            ],
            "citations": ["vendor-V-1042", "po-PO-2026-0189"],
        }
        assert list(self.v.iter_errors(payload)) == []

    def test_needs_review_verdict(self):
        payload = {
            "verdict": "needs_review",
            "reasons": [
                {"check": "duplicate", "severity": "warning", "detail": "matches INV-2025-187"},
            ],
        }
        assert list(self.v.iter_errors(payload)) == []

    def test_invalid_verdict_enum(self):
        payload = {"verdict": "maybe", "reasons": []}
        errors = list(self.v.iter_errors(payload))
        assert errors
        assert any("verdict" in str(e.absolute_path) or "enum" in str(e.message).lower() for e in errors)

    def test_invalid_check_enum(self):
        payload = {
            "verdict": "pass",
            "reasons": [{"check": "vibes", "severity": "pass", "detail": "..."}],
        }
        errors = list(self.v.iter_errors(payload))
        assert errors


class TestApPostingRecordSchema:
    """ap_posting_record — flat enum + if/then/else conditional."""

    def setup_method(self):
        self.v = Draft202012Validator(SCHEMAS["ap_posting_record"])

    def test_post_action_requires_posting_id(self):
        good = {"action": "post", "invoice": {}, "posting_id": "POST-2026-0042"}
        assert list(self.v.iter_errors(good)) == []

        # action=post WITHOUT posting_id should fail via if/then
        bad = {"action": "post", "invoice": {}}
        errors = list(self.v.iter_errors(bad))
        assert errors, "action=post without posting_id should fail"

    def test_escalate_action_requires_escalation_reason(self):
        good = {
            "action": "escalate",
            "invoice": {},
            "escalation_reason": "Vendor not in master",
        }
        assert list(self.v.iter_errors(good)) == []

        bad = {"action": "escalate", "invoice": {}}
        errors = list(self.v.iter_errors(bad))
        assert errors, "action=escalate without escalation_reason should fail"

    def test_action_enum_strict(self):
        payload = {"action": "ignore", "invoice": {}}
        errors = list(self.v.iter_errors(payload))
        assert errors


class TestResolveSchemaRef:
    """SkillMetadata.extraction_schema → JSON Schema dict resolution."""

    def test_returns_none_for_none(self):
        assert resolve_schema_ref(None) is None

    def test_named_reference_resolves(self):
        result = resolve_schema_ref("ap_invoice")
        assert result is SCHEMAS["ap_invoice"]

    def test_inline_dict_passes_through(self):
        inline = {"type": "object", "properties": {"x": {"type": "string"}}}
        result = resolve_schema_ref(inline)
        assert result is inline

    def test_unknown_named_ref_raises_with_helpful_message(self):
        with pytest.raises(ValueError) as ei:
            resolve_schema_ref("not_a_real_schema")
        assert "not_a_real_schema" in str(ei.value)
        # Error message lists available names so the SKILL.md author knows what to pick
        assert "ap_invoice" in str(ei.value)

    def test_wrong_type_raises(self):
        with pytest.raises(ValueError):
            resolve_schema_ref(42)  # type: ignore[arg-type]


class TestSkillMetadataAcceptsExtractionSchema:
    """SkillMetadata Pydantic model accepts the new field via alias + populate_by_name."""

    def test_named_ref(self):
        from db.models import SkillMetadata

        meta = SkillMetadata(extraction_schema="ap_invoice")
        assert meta.extraction_schema == "ap_invoice"

    def test_inline_dict(self):
        from db.models import SkillMetadata

        inline = {"type": "object", "properties": {"x": {"type": "string"}}}
        meta = SkillMetadata(extraction_schema=inline)
        assert meta.extraction_schema == inline

    def test_alias_serialization(self):
        """Firestore round-trip uses camelCase alias `extractionSchema`."""
        from db.models import SkillMetadata

        meta = SkillMetadata(extraction_schema="ap_verdict")
        dumped = meta.model_dump(by_alias=True)
        assert "extractionSchema" in dumped
        assert dumped["extractionSchema"] == "ap_verdict"

    def test_alias_deserialization(self):
        from db.models import SkillMetadata

        meta = SkillMetadata.model_validate({"extractionSchema": "ap_posting_record"})
        assert meta.extraction_schema == "ap_posting_record"

    def test_defaults_to_none(self):
        from db.models import SkillMetadata

        meta = SkillMetadata()
        assert meta.extraction_schema is None
