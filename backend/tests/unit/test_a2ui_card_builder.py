"""Unit tests for the schema-driven A2UI Card builder.

The builder is the bridge between schema-validated extraction output and a
nice-looking A2UI Card in the chat — replacing the JSON code block that
used to leak into bubbles for every skill with ``metadata.extractionSchema``
declared. Tests cover:

  - Envelope shape (createSurface + updateComponents + updateDataModel)
  - BasicCatalog component usage (Column root, Text, Row, Divider only)
  - Schema-driven labels (property.title preferred over key)
  - Scalar formatting (currency 2dp, booleans → ✓/✗, None → em-dash)
  - Array-of-objects rendered as a header row + body rows
  - Missing optional fields skipped (no empty rows)
  - Degraded fallback when the builder hits an unexpected schema shape
"""

from __future__ import annotations

from typing import Any

from adk.a2ui_card_builder import build_a2ui_card_from_schema


def _by_id(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in components}


# --- Envelope ---


def test_envelope_is_three_v09_messages_in_order():
    """The builder returns exactly createSurface → updateComponents → updateDataModel."""
    messages = build_a2ui_card_from_schema(
        schema={"title": "X", "properties": {"a": {"type": "string"}}},
        data={"a": "1"},
    )
    assert len(messages) == 3
    for m in messages:
        assert m["version"] == "v0.9"
    assert "createSurface" in messages[0]
    assert "updateComponents" in messages[1]
    assert "updateDataModel" in messages[2]
    # All three messages MUST share the same surfaceId so the renderer
    # threads them into one surface.
    sids = {
        messages[0]["createSurface"]["surfaceId"],
        messages[1]["updateComponents"]["surfaceId"],
        messages[2]["updateDataModel"]["surfaceId"],
    }
    assert sids == {"chat"}


def test_create_surface_advertises_basic_catalog_v09():
    """The catalogId must match the published BasicCatalog spec URL so a
    catalog-validating client (e.g. Gemini Enterprise) accepts the surface."""
    messages = build_a2ui_card_from_schema(schema={}, data={})
    catalog = messages[0]["createSurface"]["catalogId"]
    assert catalog == "https://a2ui.org/specification/v0_9/basic_catalog.json"


def test_surface_id_override_is_threaded_through_all_messages():
    messages = build_a2ui_card_from_schema(schema={"title": "X"}, data={}, surface_id="workspace")
    assert messages[0]["createSurface"]["surfaceId"] == "workspace"
    assert messages[1]["updateComponents"]["surfaceId"] == "workspace"
    assert messages[2]["updateDataModel"]["surfaceId"] == "workspace"


# --- Component tree ---


def test_root_component_id_is_root_and_type_is_column():
    """BasicCatalog hardcodes root id as 'root'. Forgetting this fails validation."""
    messages = build_a2ui_card_from_schema(
        schema={"title": "X", "properties": {"a": {"type": "string"}}}, data={"a": "1"}
    )
    components = messages[1]["updateComponents"]["components"]
    root = _by_id(components)["root"]
    assert root["component"] == "Column"
    assert isinstance(root["children"], list)


def test_only_basic_catalog_components_are_emitted():
    """Restricted component set per the Gemini Enterprise / A2UI integration
    guide. Anything outside this set would fail GE's catalog validation."""
    allowed = {"Column", "Row", "Text", "Divider"}
    messages = build_a2ui_card_from_schema(
        schema={
            "title": "Invoice",
            "properties": {
                "vendor": {"type": "string"},
                "line_items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"description": {"type": "string"}}},
                },
            },
        },
        data={"vendor": "Acme", "line_items": [{"description": "A"}]},
    )
    components = messages[1]["updateComponents"]["components"]
    types = {c["component"] for c in components}
    unknown = types - allowed
    assert unknown == set(), f"non-BasicCatalog components emitted: {unknown}"


def test_schema_title_appears_as_h2():
    messages = build_a2ui_card_from_schema(
        schema={"title": "AP Invoice", "properties": {"x": {"type": "string"}}}, data={"x": "1"}
    )
    components = messages[1]["updateComponents"]["components"]
    title_texts = [c for c in components if c["component"] == "Text" and c.get("variant") == "h2"]
    assert any(c["text"] == "AP Invoice" for c in title_texts)


def test_fallback_title_used_when_schema_has_none():
    messages = build_a2ui_card_from_schema(
        schema={"properties": {"x": {"type": "string"}}},
        data={"x": "1"},
        fallback_title="Custom Fallback",
    )
    components = messages[1]["updateComponents"]["components"]
    assert any(c.get("variant") == "h2" and c.get("text") == "Custom Fallback" for c in components)


# --- Label resolution ---


def test_label_prefers_property_title_over_key():
    """If the schema declares property.title, use it verbatim — don't humanise."""
    messages = build_a2ui_card_from_schema(
        schema={
            "title": "X",
            "properties": {"po_reference": {"type": "string", "title": "Purchase Order"}},
        },
        data={"po_reference": "PO-1"},
    )
    components = messages[1]["updateComponents"]["components"]
    captions = [c for c in components if c.get("variant") == "caption"]
    assert any(c.get("text") == "Purchase Order" for c in captions)


def test_label_humanises_snake_case_key_when_no_title():
    messages = build_a2ui_card_from_schema(
        schema={"title": "X", "properties": {"po_reference": {"type": "string"}}},
        data={"po_reference": "PO-1"},
    )
    components = messages[1]["updateComponents"]["components"]
    captions = [c for c in components if c.get("variant") == "caption"]
    assert any(c.get("text") == "Po Reference" for c in captions)


# --- Scalar formatting ---


def test_currency_field_formats_to_two_decimal_places():
    """Heuristic: any property whose title contains 'total/amount/tax/price'
    is rendered with 2dp + thousands separators. This is the difference
    between '8500.0' and '8,500.00' in the Card."""
    messages = build_a2ui_card_from_schema(
        schema={"title": "X", "properties": {"total": {"type": "number", "title": "Total"}}},
        data={"total": 8500},
    )
    components = messages[1]["updateComponents"]["components"]
    texts = [c["text"] for c in components if c["component"] == "Text"]
    assert "8,500.00" in texts


def test_boolean_renders_as_check_or_cross():
    messages = build_a2ui_card_from_schema(
        schema={"title": "X", "properties": {"approved": {"type": "boolean"}}},
        data={"approved": True},
    )
    components = messages[1]["updateComponents"]["components"]
    texts = [c["text"] for c in components if c["component"] == "Text"]
    assert "✓" in texts


def test_missing_optional_field_is_skipped_not_rendered_empty():
    """Schemas often declare optional fields. Missing values must not produce
    empty rows that hurt readability."""
    messages = build_a2ui_card_from_schema(
        schema={
            "title": "X",
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        },
        data={"a": "value-a"},  # b missing
    )
    components = messages[1]["updateComponents"]["components"]
    text_blobs = [c["text"] for c in components if c["component"] == "Text"]
    assert "value-a" in text_blobs
    # No row should have been emitted with b's label.
    # b would have humanised to "B" — and we only render label/value pairs
    # for keys present in data.
    assert "B" not in text_blobs


# --- Array-of-objects (line items table) ---


def test_array_of_objects_renders_header_row_then_one_row_per_item():
    messages = build_a2ui_card_from_schema(
        schema={
            "title": "Invoice",
            "properties": {
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "title": "Description"},
                            "quantity": {"type": "number", "title": "Qty"},
                            "amount": {"type": "number", "title": "Amount"},
                        },
                    },
                }
            },
        },
        data={
            "line_items": [
                {"description": "Cloud Infra", "quantity": 1, "amount": 4500.0},
                {"description": "Managed DB", "quantity": 1, "amount": 1800.0},
            ]
        },
    )
    components = messages[1]["updateComponents"]["components"]
    rows = [c for c in components if c["component"] == "Row"]
    # Header row + 2 data rows = 3 rows minimum.
    assert len(rows) >= 3
    # Find a Text with "Cloud Infra" — confirms data made it through.
    texts = [c["text"] for c in components if c["component"] == "Text"]
    assert "Cloud Infra" in texts
    assert "Managed DB" in texts
    # Amount column uses currency formatting (2dp + comma).
    assert "4,500.00" in texts


def test_empty_array_does_not_emit_table_section():
    """Empty array → no section heading, no header row. Keeps the card tidy
    when the extraction produced zero items."""
    messages = build_a2ui_card_from_schema(
        schema={
            "title": "Invoice",
            "properties": {"line_items": {"type": "array", "items": {"type": "object"}}},
        },
        data={"line_items": []},
    )
    components = messages[1]["updateComponents"]["components"]
    texts = [c.get("text") for c in components if c["component"] == "Text"]
    assert "Line Items" not in texts


# --- Defensive: degraded path ---


def test_builder_does_not_crash_on_malformed_schema():
    """The callback path must keep working even if the schema is unusual.
    A degraded Card is acceptable; an exception isn't."""
    messages = build_a2ui_card_from_schema(
        schema={"weird": "not a real schema"}, data={"a": "b"}, fallback_title="Result"
    )
    assert len(messages) == 3
    components = messages[1]["updateComponents"]["components"]
    assert any(c.get("id") == "root" for c in components)
