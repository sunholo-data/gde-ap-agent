// JSON → A2UI v0.9 Card builder (frontend).
//
// Why this lives in the frontend
// -------------------------------
// Earlier this sprint we tried emitting the A2UI Card from
// backend/tools/structured_extraction.py by synthesising
// `send_a2ui_json_to_client` function_call + function_response Parts on
// the after_agent_callback's returned Content. The genai SDK strips
// function_response Parts from role="model" Content (semantically
// function_response is a tool→model message, not a model→user one), so
// only the function_call survived and the frontend saw a tool call that
// never resolved. The full diagnostic is in the 2026-06-02 commit
// history.
//
// Doing the render frontend-side avoids the whole synthesis problem.
// We detect JSON-only text in a chat bubble and turn it into an A2UI v0.9
// message array using BasicCatalog components only — the same renderer
// path A2UI tool results already flow through. No protocol hackery, no
// fake tool calls.
//
// Trade-off vs. the abandoned backend approach: we don't have the JSON
// Schema on the frontend, so labels are humanised from keys
// (vendor_name → "Vendor Name") and currency formatting is heuristic
// (numeric fields whose name contains total/amount/tax/price/subtotal
// get 2dp + thousands separators). When richer labelling is needed, a
// future iteration can have the backend send the schema alongside the
// JSON via a custom message Part, but for the AP shapes the heuristic is
// already accurate.

const BASIC_CATALOG_ID =
  "https://a2ui.org/specification/v0_9/basic_catalog.json";
const A2UI_VERSION = "v0.9";

export interface BuildOpts {
  /** Fallback title when the JSON shape doesn't suggest a better one.
   * Defaults to "Result". */
  fallbackTitle?: string;
  /** Surface id for the createSurface message. Defaults to "chat" so the
   * Card renders inline in the bubble where the JSON text used to land. */
  surfaceId?: string;
}

/**
 * Turn an arbitrary JSON object into an A2UI v0.9 message array that
 * renders as a Card. Returns `null` for inputs we shouldn't render
 * (non-objects, empty objects).
 *
 * Output shape: [createSurface, updateComponents, updateDataModel] using
 * BasicCatalog components only (Column, Row, Text, Divider). The
 * resulting array is identical in structure to what the
 * `send_a2ui_json_to_client` tool emits, so the existing A2UIRenderer
 * can consume it without changes.
 */
export function buildA2UICardFromJson(
  data: unknown,
  opts: BuildOpts = {},
): Record<string, unknown>[] | null {
  if (!isPlainObject(data)) return null;
  const keys = Object.keys(data);
  if (keys.length === 0) return null;

  const surfaceId = opts.surfaceId ?? "chat";
  const fallbackTitle = opts.fallbackTitle ?? "Result";

  const b = new CardBuilder();
  const bodyChildren: string[] = [];

  const title = inferTitle(data, fallbackTitle);
  bodyChildren.push(b.text(title, "h2"));
  bodyChildren.push(b.divider());

  const [scalarKeys, arrayKeys] = partitionKeys(data);

  for (const key of scalarKeys) {
    const labelId = b.text(humanise(key), "caption");
    const valueId = b.text(formatScalar((data as Record<string, unknown>)[key], key));
    bodyChildren.push(b.row([labelId, valueId]));
  }

  for (const key of arrayKeys) {
    const items = (data as Record<string, unknown>)[key];
    if (!Array.isArray(items) || items.length === 0) continue;
    bodyChildren.push(b.divider());
    bodyChildren.push(b.text(humanise(key), "h3"));
    bodyChildren.push(...b.tableRows(items));
  }

  b.columnRoot(bodyChildren);

  return [
    {
      version: A2UI_VERSION,
      createSurface: { surfaceId, catalogId: BASIC_CATALOG_ID },
    },
    {
      version: A2UI_VERSION,
      updateComponents: { surfaceId, components: b.components },
    },
    {
      version: A2UI_VERSION,
      updateDataModel: { surfaceId, value: {} },
    },
  ];
}

// ───────────────────────── internals ─────────────────────────

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function partitionKeys(
  data: Record<string, unknown>,
): [scalars: string[], arrays: string[]] {
  const scalars: string[] = [];
  const arrays: string[] = [];
  for (const key of Object.keys(data)) {
    const v = data[key];
    // Empty arrays are dropped entirely — no row, no section. There's no
    // meaningful value to show, and "Line Items: 0 items" is noise.
    if (Array.isArray(v) && v.length === 0) continue;
    if (Array.isArray(v) && isPlainObject(v[0])) {
      arrays.push(key);
    } else {
      scalars.push(key);
    }
  }
  return [scalars, arrays];
}

/** snake_case / kebab-case → Title Case. */
function humanise(key: string): string {
  return key
    .replace(/-/g, "_")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** Light type-aware stringification — em-dash for nullish, ✓/✗ for booleans,
 * 2dp + commas for "money-shaped" numeric fields. */
function formatScalar(value: unknown, key: string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "number") {
    if (looksLikeMoneyKey(key)) {
      return value.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    return String(value);
  }
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (isPlainObject(value)) return JSON.stringify(value);
  return String(value);
}

function looksLikeMoneyKey(key: string): boolean {
  const k = key.toLowerCase();
  return (
    k.includes("total") ||
    k.includes("amount") ||
    k.includes("price") ||
    k.includes("tax") ||
    k.includes("subtotal")
  );
}

/** Heuristic title inference for the AP shapes shipped in this submission.
 * Falls back to the supplied default when nothing matches. */
function inferTitle(data: Record<string, unknown>, fallback: string): string {
  if ("vendor_name" in data && "line_items" in data) return "Invoice";
  if ("verdict" in data || "validation_result" in data) return "Validation Result";
  if ("posting_id" in data || "ap_posting_record" in data) return "Posting Record";
  if ("status" in data && "reasons" in data) return "Result";
  return fallback;
}

interface A2UIComponent {
  id: string;
  component: string;
  text?: string;
  variant?: string;
  children?: string[];
}

class CardBuilder {
  components: A2UIComponent[] = [];
  private counter = 0;

  private newId(prefix: string): string {
    this.counter += 1;
    return `${prefix}${this.counter}`;
  }

  text(text: string, variant?: "h2" | "h3" | "caption" | "body"): string {
    const id = this.newId("t");
    const comp: A2UIComponent = { id, component: "Text", text: String(text) };
    if (variant) comp.variant = variant;
    this.components.push(comp);
    return id;
  }

  divider(): string {
    const id = this.newId("d");
    this.components.push({ id, component: "Divider" });
    return id;
  }

  row(childIds: string[]): string {
    const id = this.newId("r");
    this.components.push({ id, component: "Row", children: childIds });
    return id;
  }

  columnRoot(childIds: string[]): void {
    // BasicCatalog validator requires root.id === "root".
    this.components.push({
      id: "root",
      component: "Column",
      children: childIds,
    });
  }

  /** Render an array of object items as a header row + one row per item.
   * Column set = union of keys across items, preserving insertion order
   * from the first item. */
  tableRows(items: unknown[]): string[] {
    const columns: string[] = [];
    const seen = new Set<string>();
    for (const item of items) {
      if (!isPlainObject(item)) continue;
      for (const k of Object.keys(item)) {
        if (!seen.has(k)) {
          columns.push(k);
          seen.add(k);
        }
      }
    }
    if (columns.length === 0) return [];

    const rows: string[] = [];
    const headerCells = columns.map((c) => this.text(humanise(c), "caption"));
    rows.push(this.row(headerCells));

    for (const item of items) {
      if (!isPlainObject(item)) {
        rows.push(this.row([this.text(String(item))]));
        continue;
      }
      const cells = columns.map((c) => this.text(formatScalar(item[c], c)));
      rows.push(this.row(cells));
    }
    return rows;
  }
}
