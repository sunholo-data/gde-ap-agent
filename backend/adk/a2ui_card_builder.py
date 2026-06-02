"""Schema-driven A2UI Card builder — generic, used by every extractionSchema skill.

Why this exists
---------------

Skills that declare ``metadata.extractionSchema`` in their SKILL.md run their
final response through ``backend/tools/structured_extraction.py``, which
appends the schema-validated JSON as the agent's last TEXT_MESSAGE. Without
help, that JSON renders in the chat as a fenced code block — the exact
anti-pattern Google's Gemini Enterprise / A2UI integration guide warns
against (`cloud.google.com/blog/topics/developers-practitioners/guide-to-gemini-enterprise-and-a2ui-integration`).

This module walks the JSON Schema + the validated data and emits an A2UI
v0.9 message array that renders the same content as a *Card with a table*
— using BasicCatalog components only, so Gemini Enterprise renders it
identically to the in-repo frontend.

One implementation, every schema-driven skill benefits: today
``invoice-extractor`` (ap_invoice), ``ap-validator`` (validation result),
``ap-poster`` (ap_posting_record), and any fork that declares
``extractionSchema``.

Layout
------

::

    Column (root)
    ├── Text  <schema title>                       [variant h2]
    ├── Text  <schema description>                 [variant caption]   (if present)
    ├── Divider
    ├── Row [Text "Vendor", Text "Acme GmbH"]      ──┐
    ├── Row [Text "Invoice #", Text "INV-..."]       ├── scalar fields
    ├── ...                                          ──┘
    ├── Divider                                                          (before each array section)
    ├── Text  "Line items"                         [variant h3]
    ├── Row [Text "Description", Text "Qty", ...]                        (table header)
    ├── Row [Text "Cloud Infra", Text "1", ...]                          (one row per array element)
    └── ...

Trade-offs
----------

- **Inline pattern**, not decoupled. Values are baked into Text components
  rather than bound via ``{"path": "/..."}`` against an updateDataModel.
  The decoupled pattern is more token-efficient for long conversations but
  adds an indirection that's overkill for one-shot extraction results.
  The shape is identical from BasicCatalog's perspective — switching to
  decoupled later is a callback-side change with no protocol break.

- **BasicCatalog v0.9 only.** Only ``Column``, ``Row``, ``Text``,
  ``Divider`` are used here. That's enough for the AP shapes and stays
  inside the pre-approved set Gemini Enterprise validates against.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/basic_catalog.json"
_A2UI_VERSION = "v0.9"


def build_a2ui_card_from_schema(
    *,
    schema: dict[str, Any],
    data: dict[str, Any],
    surface_id: str = "chat",
    fallback_title: str = "Extraction result",
) -> list[dict[str, Any]]:
    """Build an A2UI v0.9 message array rendering ``data`` per ``schema``.

    Args:
        schema: JSON Schema dict the data was validated against. May supply
            ``title``, ``description``, and per-property ``title`` /
            ``description`` for labelling. Order of ``properties`` is
            preserved for display order.
        data: Validated data dict to render. Missing properties are skipped
            silently (no empty rows) — schema-required fields will have
            been caught earlier by the validator.
        surface_id: A2UI surface id. Defaults to ``"chat"`` (inline bubble);
            pass ``"workspace"`` to route to the persistent workspace pane.
        fallback_title: Used when the schema declares no ``title``.

    Returns:
        A list of three v0.9 messages: ``createSurface`` →
        ``updateComponents`` → ``updateDataModel``. The data model is
        emitted as a minimal stub for forward-compat (a future decoupled-
        pattern revision can move values out of inline Text into
        ``{"path": ...}`` refs without changing the message shape).

    Raises:
        Nothing — bad input produces a degraded but valid Card with the
        raw JSON in a code-like Text rather than crashing the callback.
    """
    builder = _CardBuilder()

    try:
        title = str(schema.get("title") or fallback_title)
        description = schema.get("description")

        body_children: list[str] = []
        body_children.append(builder.text(title, variant="h2"))
        if description:
            body_children.append(builder.text(str(description), variant="caption"))
        body_children.append(builder.divider())

        scalar_keys, array_keys = _partition_properties(schema, data)

        # Scalars first — one Row per scalar field. Skipping missing keys
        # keeps the Card compact for partial extractions (e.g. a docparse
        # result without a po_reference doesn't show an empty "PO ref" row).
        for key in scalar_keys:
            prop_schema = schema.get("properties", {}).get(key, {})
            label = _label_for(key, prop_schema)
            value = _format_scalar(data.get(key), prop_schema)
            body_children.append(builder.row([builder.text(label, variant="caption"), builder.text(value)]))

        # Array-of-object sections — each gets a divider, a heading, a
        # header row of column labels, and one row per element. Empty
        # arrays are skipped entirely (no divider, no heading) so the
        # card stays tidy when the extraction returned zero items.
        for key in array_keys:
            prop_schema = schema.get("properties", {}).get(key, {})
            items = data.get(key) or []
            if not items:
                continue
            heading = _label_for(key, prop_schema)
            item_schema = (prop_schema.get("items") or {}) if isinstance(prop_schema, dict) else {}
            body_children.append(builder.divider())
            body_children.append(builder.text(heading, variant="h3"))
            body_children.extend(builder.table_rows(item_schema, items))

        builder.column_root(body_children)
    except Exception as exc:  # pragma: no cover - defensive: never break the callback
        logger.warning("a2ui_card_builder: degraded card due to %s", exc, exc_info=True)
        builder = _CardBuilder()
        builder.column_root(
            [builder.text(fallback_title, variant="h2"), builder.text(f"(failed to render card: {exc})")]
        )

    return [
        {
            "version": _A2UI_VERSION,
            "createSurface": {"surfaceId": surface_id, "catalogId": _BASIC_CATALOG_ID},
        },
        {
            "version": _A2UI_VERSION,
            "updateComponents": {"surfaceId": surface_id, "components": builder.components},
        },
        # Minimal data-model stub — kept so consumers expecting all four
        # message types in v0.9 (createSurface / updateComponents /
        # updateDataModel / deleteSurface) see a complete envelope. When
        # the decoupled-pattern revision lands, values move from inline
        # Text into this dict and the components reference them by path.
        {
            "version": _A2UI_VERSION,
            "updateDataModel": {"surfaceId": surface_id, "value": {}},
        },
    ]


# ───────────────────────── internals ─────────────────────────


def _partition_properties(schema: dict[str, Any], data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Split schema properties into (scalar_keys, array_of_object_keys).

    Only keys present in ``data`` are returned — missing optional fields
    don't create empty rows. Nested objects are folded into the scalar
    bucket and rendered as their JSON repr; deep recursion is intentionally
    out of scope for v1.
    """
    scalars: list[str] = []
    arrays: list[str] = []
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    for key in properties:
        if key not in data:
            continue
        prop_schema = properties[key] or {}
        if _is_array_of_objects(prop_schema):
            arrays.append(key)
        else:
            scalars.append(key)
    return scalars, arrays


def _is_array_of_objects(prop_schema: dict[str, Any]) -> bool:
    if not isinstance(prop_schema, dict):
        return False
    if prop_schema.get("type") != "array":
        return False
    items = prop_schema.get("items") or {}
    return isinstance(items, dict) and items.get("type") == "object"


def _label_for(key: str, prop_schema: dict[str, Any]) -> str:
    """Human-readable label — prefers schema.title, falls back to humanised key."""
    if isinstance(prop_schema, dict):
        title = prop_schema.get("title")
        if isinstance(title, str) and title:
            return title
    # snake_case / kebab-case → Title Case.
    return " ".join(part.capitalize() for part in key.replace("-", "_").split("_") if part)


def _format_scalar(value: Any, prop_schema: dict[str, Any]) -> str:
    """Stringify a scalar with a few light type-aware niceties.

    - Numbers with format=='currency' or schema hint show 2dp.
    - Booleans render as ✓/✗ (still valid Text — no widget swap).
    - None / missing → em-dash to keep row heights stable.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, (int, float)):
        # Heuristic: money-shaped fields get 2dp. We avoid pulling in
        # locale or Decimal here — extraction output is already typed.
        if isinstance(prop_schema, dict) and (
            prop_schema.get("format") == "currency"
            or prop_schema.get("x-display") == "currency"
            or any(
                hint in (prop_schema.get("title") or "").lower()
                for hint in ("amount", "total", "price", "tax", "subtotal")
            )
        ):
            return f"{float(value):,.2f}"
        return str(value)
    if isinstance(value, (list, dict)):
        # Fallback for nested structures we didn't promote to their own section.
        import json as _json

        return _json.dumps(value, ensure_ascii=False)
    return str(value)


class _CardBuilder:
    """Accumulates flat A2UI components with auto-generated unique ids.

    BasicCatalog references children by string id, so the renderer needs a
    flat list with stable ids. The first added component is conventionally
    named ``root``; everything else gets a generated id.
    """

    def __init__(self) -> None:
        self.components: list[dict[str, Any]] = []
        self._counter = 0

    def _new_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def text(self, text: str, *, variant: str | None = None) -> str:
        cid = self._new_id("t")
        comp: dict[str, Any] = {"id": cid, "component": "Text", "text": str(text)}
        if variant:
            comp["variant"] = variant
        self.components.append(comp)
        return cid

    def divider(self) -> str:
        cid = self._new_id("d")
        self.components.append({"id": cid, "component": "Divider"})
        return cid

    def row(self, child_ids: list[str]) -> str:
        cid = self._new_id("r")
        self.components.append({"id": cid, "component": "Row", "children": list(child_ids)})
        return cid

    def column_root(self, child_ids: list[str]) -> str:
        # The catalog validator hardcodes root id == "root"; this is the
        # only component we name explicitly rather than via the counter.
        self.components.append({"id": "root", "component": "Column", "children": list(child_ids)})
        return "root"

    def table_rows(self, item_schema: dict[str, Any], items: list[Any]) -> list[str]:
        """Render an array-of-objects as a header row + one row per element.

        Column set = the union of keys in items (preserving the order from
        ``item_schema.properties`` when available, falling back to insertion
        order from the first item). Keeps the table stable when an
        individual line item omits an optional field.
        """
        if not items:
            return []

        # Determine column order: schema order first, then any extra keys
        # present in items that the schema didn't enumerate.
        schema_props = list((item_schema.get("properties") or {}).keys()) if isinstance(item_schema, dict) else []
        seen: set[str] = set(schema_props)
        for item in items:
            if isinstance(item, dict):
                for k in item:
                    if k not in seen:
                        schema_props.append(k)
                        seen.add(k)
        columns = schema_props

        added: list[str] = []
        # Header row uses caption variant; label per column from schema.
        header_cells = [
            self.text(_label_for(c, (item_schema.get("properties") or {}).get(c, {})), variant="caption")
            for c in columns
        ]
        added.append(self.row(header_cells))

        # Body rows — one per item. Cells render via _format_scalar so
        # numeric formatting matches the scalar rows above.
        for item in items:
            if not isinstance(item, dict):
                added.append(self.row([self.text(str(item))]))
                continue
            cells = [
                self.text(
                    _format_scalar(item.get(c), (item_schema.get("properties") or {}).get(c, {})),
                )
                for c in columns
            ]
            added.append(self.row(cells))

        return added
