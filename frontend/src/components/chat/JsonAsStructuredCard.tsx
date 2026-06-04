"use client";

/**
 * Render an arbitrary JSON object as a structured card using native React
 * + the DefinitionList primitive.
 *
 * Sibling to JsonAsA2UICard. The A2UI version goes through @a2ui/react's
 * Row component which has no fixed-label-column convention — long labels
 * like "Invoice Number" wrap onto two lines and crowd the value, which
 * is the cramped feel the audit panes and inline emit_* cards suffer
 * from. This version owns its own layout: labels live in a fixed-width
 * left column, values flow on the right with monospace tabular-nums for
 * money/IDs, hairline section dividers, and nested objects/arrays render
 * as labelled sub-sections rather than stringified blobs.
 *
 * Used in audit InputOutputCard, MessageBubble inline emit_* cards, and
 * the Workbench Invoice tab summary. The workspace `A2UISurfaceMount`
 * pipeline (backend-emitted A2UI messages) is untouched — that's still
 * "real A2UI on the wire" for protocol-purity claims.
 */

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { DefinitionList, type DefinitionItem } from "@/components/shared/DefinitionList";

const ADK_TOOL_RESULT_WRAPPER_KEY = "result";
const NESTED_MAX_DEPTH = 2;

export interface JsonAsStructuredCardProps {
  /** JSON object/array/string. Accepts the same inputs as JsonAsA2UICard. */
  value: unknown;
  /** Title displayed at the top of the card when no shape-based title fits. */
  fallbackTitle?: string;
  /** Outer wrapper class. */
  className?: string;
  /** Compact variant for inline (chat bubble) usage. */
  compact?: boolean;
  /** Message shown when value can't be rendered. */
  fallbackMessage?: string;
}

export function JsonAsStructuredCard({
  value,
  fallbackTitle = "Result",
  className,
  compact = false,
  fallbackMessage,
}: JsonAsStructuredCardProps) {
  const parsed = useMemo(() => unwrap(parseInput(value)), [value]);

  // Plain string fallback — muted preview, never a raw blob.
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    const text =
      typeof parsed === "string"
        ? parsed
        : parsed === null
          ? ""
          : JSON.stringify(parsed);
    return (
      <div
        className={cn(
          "rounded-md border border-border bg-muted/30 px-3 py-2 text-xs italic text-muted-foreground",
          className,
        )}
      >
        {text || fallbackMessage || "(no structured output)"}
      </div>
    );
  }

  const data = parsed as Record<string, unknown>;
  const title = inferTitle(data, fallbackTitle);
  const sections = buildSections(data);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border bg-background",
        className,
      )}
    >
      <header className="flex items-center justify-between border-b border-border bg-muted/20 px-4 py-2">
        <h3 className="font-display text-sm font-semibold tracking-tight text-foreground">
          {title}
        </h3>
        {!compact && (
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/70">
            A2UI Card
          </span>
        )}
      </header>

      <div className={cn("space-y-4", compact ? "p-3" : "p-4")}>
        {sections.map((section, i) => (
          <Section
            key={`${section.heading ?? "root"}-${i}`}
            heading={section.heading}
            items={section.items}
            tableRows={section.tableRows}
            tableHeaders={section.tableHeaders}
            compact={compact}
          />
        ))}
      </div>
    </div>
  );
}

// ─── section building ──────────────────────────────────────────────────────

interface BuiltSection {
  heading?: string;
  items: DefinitionItem[];
  /** Object-array sections render as a small table — header row + rows. */
  tableHeaders?: string[];
  tableRows?: string[][];
}

function buildSections(data: Record<string, unknown>, depth = 0): BuiltSection[] {
  if (depth >= NESTED_MAX_DEPTH + 1) return [];

  const normalised = unwrapStringEncodedNested(data);
  const { scalars, arrays, nested } = partition(normalised);

  const sections: BuiltSection[] = [];

  // Root scalars as the first un-headed section.
  if (scalars.length > 0) {
    sections.push({
      items: scalars.map((key) => ({
        label: humanise(key),
        value: renderScalar(normalised[key], key),
        valueClassName: looksLikeNumeric(key, normalised[key])
          ? "font-mono tabular-nums"
          : undefined,
      })),
    });
  }

  // Nested objects → labelled section, recurse (one level deep).
  for (const key of nested) {
    const subValue = normalised[key];
    if (!isPlainObject(subValue)) continue;
    const subSections = buildSections(subValue, depth + 1);
    if (subSections.length === 0) continue;
    // Inline the first sub-section's items under our heading; emit any
    // deeper sub-sections as their own.
    const [first, ...rest] = subSections;
    sections.push({ heading: humanise(key), items: first.items, tableHeaders: first.tableHeaders, tableRows: first.tableRows });
    for (const r of rest) sections.push(r);
  }

  // Array-of-objects → table.
  for (const key of arrays) {
    const items = normalised[key];
    if (!Array.isArray(items) || items.length === 0) continue;
    if (!isPlainObject(items[0])) continue;
    const headers: string[] = [];
    const seen = new Set<string>();
    for (const item of items) {
      if (!isPlainObject(item)) continue;
      for (const k of Object.keys(item)) {
        if (!seen.has(k)) {
          headers.push(k);
          seen.add(k);
        }
      }
    }
    const rows: string[][] = items.map((item) => {
      if (!isPlainObject(item)) return headers.map(() => "");
      return headers.map((h) => String(renderScalar(item[h], h)));
    });
    sections.push({
      heading: humanise(key),
      items: [],
      tableHeaders: headers.map((h) => humanise(h)),
      tableRows: rows,
    });
  }

  return sections;
}

function Section({
  heading,
  items,
  tableHeaders,
  tableRows,
  compact,
}: BuiltSection & { compact: boolean }) {
  const showTable = tableHeaders && tableRows && tableHeaders.length > 0;
  const showList = items.length > 0;
  if (!showTable && !showList && !heading) return null;
  return (
    <section>
      {heading && (
        <h4 className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {heading}
        </h4>
      )}
      {showList && (
        <DefinitionList items={items} tone={compact ? "dense" : "comfortable"} />
      )}
      {showTable && (
        <div className="overflow-hidden rounded border border-border">
          <table className="w-full text-xs">
            <thead className="bg-muted/30">
              <tr>
                {tableHeaders!.map((h) => (
                  <th
                    key={h}
                    className="px-2 py-1.5 text-left font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows!.map((row, ri) => (
                <tr
                  key={ri}
                  className={cn(
                    "border-t border-border/60",
                    ri % 2 === 1 && "bg-muted/10",
                  )}
                >
                  {row.map((cell, ci) => {
                    const headerKey = tableHeaders![ci]?.toLowerCase() ?? "";
                    const numeric =
                      headerKey.includes("total") ||
                      headerKey.includes("amount") ||
                      headerKey.includes("price") ||
                      headerKey.includes("tax") ||
                      headerKey.includes("qty") ||
                      headerKey.includes("quantity");
                    return (
                      <td
                        key={ci}
                        className={cn(
                          "px-2 py-1.5 align-top",
                          numeric && "text-right font-mono tabular-nums",
                        )}
                      >
                        {cell || "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ─── helpers ──────────────────────────────────────────────────────────────

function parseInput(raw: unknown): unknown {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "string") {
    const t = raw.trim();
    if (!t) return null;
    try {
      return JSON.parse(t);
    } catch {
      return raw;
    }
  }
  return raw;
}

function unwrap(value: unknown): unknown {
  if (!isPlainObject(value)) return value;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);
  if (keys.length === 1 && keys[0] === ADK_TOOL_RESULT_WRAPPER_KEY) {
    return obj[ADK_TOOL_RESULT_WRAPPER_KEY];
  }
  return value;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function unwrapStringEncodedNested(
  data: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
        try {
          const parsed = JSON.parse(trimmed);
          if (
            (Array.isArray(parsed) && parsed.length > 0 && isPlainObject(parsed[0])) ||
            (isPlainObject(parsed) && Object.keys(parsed).length > 0)
          ) {
            const clean = key.endsWith("_json") ? key.slice(0, -5) : key;
            out[clean] = parsed;
            continue;
          }
        } catch {
          // not JSON, fall through
        }
      }
    }
    out[key] = value;
  }
  return out;
}

function partition(data: Record<string, unknown>): {
  scalars: string[];
  arrays: string[];
  nested: string[];
} {
  const scalars: string[] = [];
  const arrays: string[] = [];
  const nested: string[] = [];
  for (const key of Object.keys(data)) {
    const v = data[key];
    if (Array.isArray(v) && v.length === 0) continue;
    if (Array.isArray(v) && isPlainObject(v[0])) arrays.push(key);
    else if (isPlainObject(v) && Object.keys(v).length > 0) nested.push(key);
    else scalars.push(key);
  }
  return { scalars, arrays, nested };
}

function humanise(key: string): string {
  return key
    .replace(/-/g, "_")
    .split("_")
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

function looksLikeNumeric(key: string, value: unknown): boolean {
  if (typeof value === "number") return true;
  const k = key.toLowerCase();
  return (
    k.includes("total") ||
    k.includes("amount") ||
    k.includes("price") ||
    k.includes("tax") ||
    k.includes("subtotal") ||
    k.includes("count") ||
    k.includes("number") ||
    k.endsWith("_id") ||
    k === "id" ||
    k.includes("ref")
  );
}

function renderScalar(value: unknown, key: string): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-muted-foreground/50">—</span>;
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "number") {
    if (looksLikeMoney(key)) {
      return value.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    return String(value);
  }
  if (typeof value === "string") {
    // Highlight verdicts / statuses as chips.
    const lc = value.toLowerCase();
    if (
      (key.toLowerCase().includes("verdict") ||
        key.toLowerCase().includes("status") ||
        key.toLowerCase() === "decision") &&
      lc.length < 24
    ) {
      const tone = verdictTone(lc);
      return <Chip tone={tone}>{value}</Chip>;
    }
    return value;
  }
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (isPlainObject(value)) return JSON.stringify(value);
  return String(value);
}

function looksLikeMoney(key: string): boolean {
  const k = key.toLowerCase();
  return (
    k.includes("total") ||
    k.includes("amount") ||
    k.includes("price") ||
    k.includes("tax") ||
    k.includes("subtotal")
  );
}

function verdictTone(v: string): "success" | "warn" | "danger" | "neutral" {
  if (v.includes("post") || v.includes("approve") || v.includes("ok") || v.includes("pass")) return "success";
  if (v.includes("review") || v.includes("pending") || v.includes("hold") || v.includes("warn")) return "warn";
  if (v.includes("fail") || v.includes("reject") || v.includes("block") || v.includes("error")) return "danger";
  return "neutral";
}

function Chip({
  tone,
  children,
}: {
  tone: "success" | "warn" | "danger" | "neutral";
  children: React.ReactNode;
}) {
  const cls =
    tone === "success"
      ? "border-primary/30 bg-primary/10 text-primary"
      : tone === "warn"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
        : tone === "danger"
          ? "border-destructive/30 bg-destructive/10 text-destructive"
          : "border-border bg-muted/30 text-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
        cls,
      )}
    >
      {children}
    </span>
  );
}

function inferTitle(data: Record<string, unknown>, fallback: string): string {
  if ("vendor_name" in data && "line_items" in data) return "Invoice";
  if ("verdict" in data || "validation_result" in data) return "Validation Result";
  if ("posting_id" in data || "ap_posting_record" in data) return "Posting Record";
  if ("status" in data && "reasons" in data) return "Result";
  return fallback;
}
