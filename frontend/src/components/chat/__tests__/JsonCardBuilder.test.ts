import { describe, expect, it } from "vitest";
import { buildA2UICardFromJson } from "../JsonCardBuilder";

// Helpers — these read components out of the v0.9 envelope so the tests
// can focus on what they're actually asserting (labels, layout) without
// the boilerplate of digging into messages[1].updateComponents.components
// in every test.

interface Component {
  id: string;
  component: string;
  text?: string;
  variant?: string;
  children?: string[];
}

function components(msgs: Record<string, unknown>[] | null): Component[] {
  expect(msgs).not.toBeNull();
  const update = (msgs as Record<string, unknown>[])[1] as {
    updateComponents: { components: Component[] };
  };
  return update.updateComponents.components;
}

function texts(msgs: Record<string, unknown>[] | null): string[] {
  return components(msgs)
    .filter((c) => c.component === "Text" && typeof c.text === "string")
    .map((c) => c.text as string);
}

// ───────── Envelope ─────────

describe("buildA2UICardFromJson — envelope", () => {
  it("returns a 3-message v0.9 envelope: createSurface → updateComponents → updateDataModel", () => {
    const msgs = buildA2UICardFromJson({ a: "1" }) as Record<string, unknown>[];
    expect(msgs).not.toBeNull();
    expect(msgs).toHaveLength(3);
    for (const m of msgs) {
      expect(m.version).toBe("v0.9");
    }
    expect(msgs[0]).toHaveProperty("createSurface");
    expect(msgs[1]).toHaveProperty("updateComponents");
    expect(msgs[2]).toHaveProperty("updateDataModel");
  });

  it("advertises BasicCatalog v0.9 on createSurface", () => {
    const msgs = buildA2UICardFromJson({ a: "1" }) as Record<string, unknown>[];
    const cs = msgs[0].createSurface as Record<string, unknown>;
    expect(cs.catalogId).toBe(
      "https://a2ui.org/specification/v0_9/basic_catalog.json",
    );
    expect(cs.surfaceId).toBe("chat");
  });

  it("returns null for non-object inputs", () => {
    expect(buildA2UICardFromJson(null)).toBeNull();
    expect(buildA2UICardFromJson("string")).toBeNull();
    expect(buildA2UICardFromJson(42)).toBeNull();
    expect(buildA2UICardFromJson([1, 2, 3])).toBeNull();
  });

  it("returns null for empty objects (no signal to render)", () => {
    expect(buildA2UICardFromJson({})).toBeNull();
  });
});

// ───────── Component palette ─────────

describe("buildA2UICardFromJson — only emits BasicCatalog components", () => {
  it("never emits a component outside Column/Row/Text/Divider", () => {
    const msgs = buildA2UICardFromJson({
      vendor_name: "Acme",
      total: 100,
      line_items: [{ description: "X", amount: 50 }],
    });
    const palette = new Set(components(msgs).map((c) => c.component));
    const allowed = new Set(["Column", "Row", "Text", "Divider"]);
    const unknown = [...palette].filter((c) => !allowed.has(c));
    expect(unknown).toEqual([]);
  });

  it("has a single root Column with id='root' (BasicCatalog requirement)", () => {
    const msgs = buildA2UICardFromJson({ a: "1" });
    const roots = components(msgs).filter((c) => c.id === "root");
    expect(roots).toHaveLength(1);
    expect(roots[0].component).toBe("Column");
  });
});

// ───────── Labels ─────────

describe("buildA2UICardFromJson — label humanisation", () => {
  it("humanises snake_case keys to Title Case", () => {
    const msgs = buildA2UICardFromJson({ po_reference: "PO-1" });
    expect(texts(msgs)).toContain("Po Reference");
  });

  it("humanises kebab-case keys", () => {
    const msgs = buildA2UICardFromJson({ "vendor-id": "v-1" });
    expect(texts(msgs)).toContain("Vendor Id");
  });
});

// ───────── Title inference ─────────

describe("buildA2UICardFromJson — title inference", () => {
  it("titles invoice-shaped JSON as 'Invoice'", () => {
    // The AP demo case from the screenshot — confirms the heuristic
    // picks the right title for the most-common shape in this fork.
    const msgs = buildA2UICardFromJson({
      vendor_name: "Acme",
      line_items: [{ description: "X" }],
    });
    expect(texts(msgs)).toContain("Invoice");
  });

  it("titles validator-shaped JSON as 'Validation Result'", () => {
    const msgs = buildA2UICardFromJson({ verdict: "pass", reasons: [] });
    expect(texts(msgs)).toContain("Validation Result");
  });

  it("falls back to the provided fallbackTitle for unknown shapes", () => {
    const msgs = buildA2UICardFromJson({ random: "data" }, { fallbackTitle: "Custom" });
    expect(texts(msgs)).toContain("Custom");
  });

  it("falls back to 'Result' when no fallback is provided", () => {
    const msgs = buildA2UICardFromJson({ random: "data" });
    expect(texts(msgs)).toContain("Result");
  });
});

// ───────── Scalar formatting ─────────

describe("buildA2UICardFromJson — scalar formatting", () => {
  it("formats money-shaped numeric fields with 2dp + thousands separators", () => {
    const msgs = buildA2UICardFromJson({ total: 8500, subtotal: 7050, tax: 1450 });
    const t = texts(msgs);
    expect(t).toContain("8,500.00");
    expect(t).toContain("7,050.00");
    expect(t).toContain("1,450.00");
  });

  it("leaves non-money numbers as-is", () => {
    const msgs = buildA2UICardFromJson({ count: 42 });
    expect(texts(msgs)).toContain("42");
    // Defensive: count is not in the money heuristic — must not be 42.00.
    expect(texts(msgs)).not.toContain("42.00");
  });

  it("renders booleans as ✓ / ✗", () => {
    const msgs = buildA2UICardFromJson({ approved: true, blocked: false });
    const t = texts(msgs);
    expect(t).toContain("✓");
    expect(t).toContain("✗");
  });

  it("renders null and undefined as em-dash", () => {
    const msgs = buildA2UICardFromJson({ po_reference: null });
    expect(texts(msgs)).toContain("—");
  });

  it("renders nested objects as JSON.stringify (no Card recursion in v1)", () => {
    const msgs = buildA2UICardFromJson({ meta: { a: 1, b: 2 } });
    expect(texts(msgs)).toContain('{"a":1,"b":2}');
  });
});

// ───────── Array-of-objects → table ─────────

describe("buildA2UICardFromJson — line items as table", () => {
  it("renders an array-of-objects as a Row table with a header row + one row per item", () => {
    const msgs = buildA2UICardFromJson({
      line_items: [
        { description: "Cloud Infra", quantity: 1, amount: 4500 },
        { description: "Managed DB", quantity: 1, amount: 1800 },
      ],
    });
    const rows = components(msgs).filter((c) => c.component === "Row");
    // Header row + 2 data rows (plus possibly Row's used for label/value
    // scalar pairs from sibling fields — there are none here).
    expect(rows.length).toBeGreaterThanOrEqual(3);
    const t = texts(msgs);
    expect(t).toContain("Cloud Infra");
    expect(t).toContain("Managed DB");
    // Amount column uses money formatting (heuristic on the column name).
    expect(t).toContain("4,500.00");
  });

  it("skips array sections when the array is empty", () => {
    const msgs = buildA2UICardFromJson({
      vendor_name: "Acme",
      line_items: [],
    });
    expect(texts(msgs)).not.toContain("Line Items");
  });

  it("union-merges columns when items have different shapes", () => {
    // Item 2 introduces a `tax_code` column item 1 doesn't have. The
    // table should include all keys union-style so no data goes missing.
    const msgs = buildA2UICardFromJson({
      line_items: [
        { description: "A", amount: 10 },
        { description: "B", amount: 20, tax_code: "VAT19" },
      ],
    });
    const t = texts(msgs);
    expect(t).toContain("Tax Code");
    expect(t).toContain("VAT19");
  });
});

// ───────── End-to-end shape (the actual screenshot case) ─────────

describe("buildA2UICardFromJson — the AP invoice screenshot case", () => {
  it("renders the same JSON shape the user screenshotted as a clean Card", () => {
    // Verbatim from the user's screenshot — this is the regression case.
    const data = {
      vendor_name: "Acme GmbH",
      invoice_number: "INV-2026-042",
      invoice_date: "2026-06-01",
      due_date: "2026-07-01",
      po_reference: "PO-2026-0189",
      currency: "EUR",
      line_items: [
        {
          description: "Cloud Infrastructure Services — June 2026",
          quantity: 1,
          unit_price: 4500.0,
          amount: 4500.0,
        },
        {
          description: "Managed Database Cluster (PostgreSQL HA)",
          quantity: 1,
          unit_price: 1800.0,
          amount: 1800.0,
        },
      ],
      subtotal: 6300,
      tax: 1197,
      total: 7497,
    };
    const msgs = buildA2UICardFromJson(data);
    const t = texts(msgs);

    expect(t).toContain("Invoice"); // inferred title
    expect(t).toContain("Acme GmbH");
    expect(t).toContain("INV-2026-042");
    expect(t).toContain("PO-2026-0189");
    expect(t).toContain("Cloud Infrastructure Services — June 2026");
    expect(t).toContain("7,497.00"); // money formatting
    // No raw JSON braces in the output — that's the whole point.
    for (const text of t) {
      expect(text).not.toMatch(/^[\s]*[{[]/);
    }
  });
});
