"use client";

/**
 * InvoiceHeroCard — the primary delivery artifact of an AP pipeline run.
 *
 * Specialised renderer for invoice-shaped payloads (vendor_name + line_items).
 * Sits in the Workbench Invoice tab, inline in chat bubbles after each
 * pipeline step, and in audit InputOutputCards. Designed to feel like a
 * financial document, not a JSON pretty-printer: vendor name and total
 * are the two visual anchors, a thin status-toned accent stripe runs
 * across the top, and the line-items table reads like a ledger.
 *
 * Renders defensively from a loose payload shape — coerces strings to
 * numbers, falls back to status/verdict interchangeably, omits rows for
 * undefined fields.
 */

import { cn } from "@/lib/utils";
import { DefinitionList, type DefinitionItem } from "@/components/shared/DefinitionList";

type StatusTone = "success" | "warn" | "danger" | "neutral";

interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
}

export interface InvoiceHeroCardProps {
  /** Loose invoice payload — vendor_name + line_items expected, other
   * fields opportunistic. Accepts strings or numbers; coerces internally. */
  data: Record<string, unknown>;
  /** Outer className. */
  className?: string;
  /** Compact variant for inline chat-bubble rendering. */
  compact?: boolean;
}

export function InvoiceHeroCard({ data, className, compact = false }: InvoiceHeroCardProps) {
  const vendorName = asString(data.vendor_name) ?? "Vendor";
  const invoiceNumber = asString(data.invoice_number);
  const invoiceDate = asString(data.invoice_date);
  const dueDate = asString(data.due_date);
  const poReference = asString(data.po_reference);
  const currency = asString(data.currency) ?? "EUR";
  const subtotal = asNumber(data.subtotal);
  const tax = asNumber(data.tax);
  const total = asNumber(data.total) ?? 0;
  const glCode = asString(data.gl_code);
  const action = asString(data.action);
  const verdictReason = asString(data.verdict_reason);
  const routing = asString(data.routing);
  const escalationAssignee = asString(data.escalation_assignee);
  const slaHours = asNumber(data.sla_hours);
  const auditCitations = asString(data.audit_citations_csv);

  const rawStatus = asString(data.status) ?? asString(data.verdict) ?? "PENDING";
  const tone = statusTone(rawStatus);
  const palette = TONE[tone];

  const lineItems = coerceLineItems(data.line_items);
  const hasVerdictFooter = Boolean(verdictReason || routing || escalationAssignee || auditCitations);

  // Metadata rows — only those with a value, in deliberate reading order.
  const metaItems: DefinitionItem[] = [];
  if (invoiceDate) {
    metaItems.push({ label: "Invoice date", value: formatDate(invoiceDate) });
  }
  if (glCode) {
    metaItems.push({
      label: "GL code",
      value: <span className="font-mono text-xs">{glCode}</span>,
    });
  }
  if (action) {
    metaItems.push({
      label: "Action",
      value: (
        <span className="font-mono text-xs uppercase tracking-wider">{action}</span>
      ),
    });
  }
  metaItems.push({ label: "Currency", value: <span className="font-mono text-xs">{currency}</span> });

  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-lg border border-border bg-background shadow-[0_1px_0_0_rgba(0,0,0,0.03),0_4px_16px_-12px_rgba(0,0,0,0.08)] dark:shadow-[0_1px_0_0_rgba(255,255,255,0.04),0_4px_16px_-12px_rgba(0,0,0,0.6)]",
        className,
      )}
    >
      {/* Status-toned accent stripe — runs along the top of the card so
          the verdict registers before you read the chip. */}
      <div className={cn("absolute inset-x-0 top-0 h-[3px]", palette.stripe)} aria-hidden />

      {/* Hero band — vendor identity + status chip. */}
      <header
        className={cn(
          "flex items-start justify-between gap-4 border-b border-border bg-gradient-to-b from-muted/30 to-transparent",
          compact ? "px-4 pb-3 pt-4" : "px-6 pb-5 pt-7",
        )}
      >
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "mb-2 font-mono uppercase tracking-[0.22em] text-muted-foreground",
              compact ? "text-[9px]" : "text-[10px]",
            )}
          >
            <span>Invoice</span>
            {invoiceNumber && (
              <>
                <span aria-hidden className="mx-2 text-muted-foreground/40">·</span>
                <span className="text-foreground/80">{invoiceNumber}</span>
              </>
            )}
          </p>
          <h2
            className={cn(
              "font-display font-semibold leading-tight tracking-tight text-foreground",
              compact ? "text-xl" : "text-3xl",
            )}
          >
            {vendorName}
          </h2>
        </div>
        <StatusPill tone={tone} label={rawStatus} compact={compact} />
      </header>

      {/* Financial summary band — total is the visual anchor. */}
      <section
        className={cn(
          "grid items-end gap-x-6 gap-y-3 border-b border-border bg-muted/[0.15]",
          compact
            ? "grid-cols-1 px-4 py-4"
            : "grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] px-6 py-5",
        )}
      >
        <div>
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            Total due
          </p>
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                "font-display font-semibold leading-none tracking-tight tabular-nums text-foreground",
                compact ? "text-3xl" : "text-[2.5rem]",
              )}
            >
              {formatMoney(total)}
            </span>
            <span className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
              {currency}
            </span>
          </div>
        </div>

        {(dueDate || poReference) && (
          <dl
            className={cn(
              "grid gap-x-4 gap-y-2",
              dueDate && poReference ? "grid-cols-2" : "grid-cols-1",
              !compact && "border-l border-border/60 pl-6",
            )}
          >
            {dueDate && (
              <div>
                <dt className="mb-1 font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
                  Due
                </dt>
                <dd className="font-display text-sm font-medium tabular-nums text-foreground">
                  {formatDate(dueDate)}
                </dd>
              </div>
            )}
            {poReference && (
              <div>
                <dt className="mb-1 font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
                  PO Reference
                </dt>
                <dd className="font-mono text-sm font-medium tabular-nums text-foreground">
                  {poReference}
                </dd>
              </div>
            )}
          </dl>
        )}
      </section>

      {/* Metadata DefinitionList — dense rows for secondary detail. */}
      {metaItems.length > 0 && (
        <section className={cn(compact ? "px-4 py-3" : "px-6 py-4", "border-b border-border")}>
          {!compact && (
            <h3 className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Details
            </h3>
          )}
          <DefinitionList items={metaItems} tone="dense" />
        </section>
      )}

      {/* Line items — ledger-style table. */}
      {lineItems.length > 0 && (
        <section className={cn(compact ? "px-4 py-3" : "px-6 py-4")}>
          {!compact && (
            <h3 className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Line items
            </h3>
          )}
          <div className="overflow-hidden rounded-md border border-border/60">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/30 text-muted-foreground">
                  <th
                    scope="col"
                    className="px-3 py-2 text-left font-mono text-[10px] font-semibold uppercase tracking-wider"
                  >
                    Description
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 text-right font-mono text-[10px] font-semibold uppercase tracking-wider"
                  >
                    Qty
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 text-right font-mono text-[10px] font-semibold uppercase tracking-wider"
                  >
                    Unit
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 text-right font-mono text-[10px] font-semibold uppercase tracking-wider"
                  >
                    Amount
                  </th>
                </tr>
              </thead>
              <tbody>
                {lineItems.map((item, i) => (
                  <tr
                    key={i}
                    className={cn(
                      "border-t border-border/40 transition-colors hover:bg-muted/20",
                      i % 2 === 1 && "bg-muted/[0.08]",
                    )}
                  >
                    <td className="px-3 py-2 align-top text-foreground">{item.description}</td>
                    <td className="px-3 py-2 text-right align-top font-mono tabular-nums text-muted-foreground">
                      {item.quantity}
                    </td>
                    <td className="px-3 py-2 text-right align-top font-mono tabular-nums text-muted-foreground">
                      {formatMoney(item.unit_price)}
                    </td>
                    <td className="px-3 py-2 text-right align-top font-mono font-medium tabular-nums text-foreground">
                      {formatMoney(item.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t border-border bg-muted/[0.12]">
                {subtotal !== undefined && (
                  <tr>
                    <td colSpan={3} className="px-3 pb-1 pt-2 text-right text-xs text-muted-foreground">
                      Subtotal
                    </td>
                    <td className="px-3 pb-1 pt-2 text-right font-mono text-xs tabular-nums text-muted-foreground">
                      {formatMoney(subtotal)}
                    </td>
                  </tr>
                )}
                {tax !== undefined && (
                  <tr>
                    <td colSpan={3} className="px-3 py-1 text-right text-xs text-muted-foreground">
                      Tax
                    </td>
                    <td className="px-3 py-1 text-right font-mono text-xs tabular-nums text-muted-foreground">
                      {formatMoney(tax)}
                    </td>
                  </tr>
                )}
                <tr className="border-t-2 border-foreground/15">
                  <td
                    colSpan={3}
                    className="px-3 pb-3 pt-2 text-right font-display text-sm font-semibold tracking-tight text-foreground"
                  >
                    Total
                  </td>
                  <td className="px-3 pb-3 pt-2 text-right font-display text-base font-bold tabular-nums text-foreground">
                    {formatMoney(total)}{" "}
                    <span className="font-mono text-[10px] font-normal uppercase tracking-wider text-muted-foreground">
                      {currency}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>
      )}

      {/* Verdict footer band — status-toned, with routing/assignee/citations. */}
      {hasVerdictFooter && (
        <footer
          className={cn(
            "flex flex-col gap-2",
            compact ? "px-4 py-3" : "px-6 py-4",
            palette.footer,
          )}
        >
          {verdictReason && (
            <p
              className={cn(
                "leading-snug text-foreground",
                compact ? "text-xs" : "text-sm",
              )}
            >
              <span className={cn("font-semibold", palette.text)}>
                {toneVerbForLabel(tone)}
              </span>{" "}
              <span className="text-muted-foreground">— {verdictReason}</span>
            </p>
          )}

          {(!compact || !verdictReason) && (routing || escalationAssignee || slaHours !== undefined) && (
            <div className="flex flex-wrap items-center gap-1.5">
              {routing && <MetaChip>{routing}</MetaChip>}
              {escalationAssignee && (
                <MetaChip>
                  <span className="text-muted-foreground">Assignee · </span>
                  <span className="text-foreground">{escalationAssignee}</span>
                </MetaChip>
              )}
              {slaHours !== undefined && (
                <MetaChip>
                  <span className="text-muted-foreground">SLA · </span>
                  <span className="font-mono tabular-nums text-foreground">{slaHours}h</span>
                </MetaChip>
              )}
            </div>
          )}

          {!compact && auditCitations && (
            <div className="flex flex-wrap items-center gap-1.5">
              {auditCitations
                .split(",")
                .map((c) => c.trim())
                .filter(Boolean)
                .map((cite) => (
                  <span
                    key={cite}
                    className="inline-flex items-center rounded-sm border border-border bg-background/70 px-1.5 py-0.5 font-mono text-[10px] tracking-wider text-muted-foreground"
                  >
                    <span className="mr-1 text-[8px] uppercase tracking-[0.2em] text-muted-foreground/70">
                      Audit
                    </span>
                    <span className="text-foreground">{cite}</span>
                  </span>
                ))}
            </div>
          )}
        </footer>
      )}
    </article>
  );
}

// ─── status pill ──────────────────────────────────────────────────────────

function StatusPill({
  tone,
  label,
  compact,
}: {
  tone: StatusTone;
  label: string;
  compact: boolean;
}) {
  const palette = TONE[tone];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md border font-display font-bold uppercase tracking-wider",
        compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-xs",
        palette.chip,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", palette.dot)} aria-hidden />
      {label}
    </span>
  );
}

function MetaChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-sm border border-border/80 bg-background/60 px-2 py-0.5 text-[11px] tabular-nums">
      {children}
    </span>
  );
}

// ─── status tone palette ───────────────────────────────────────────────────

const TONE: Record<
  StatusTone,
  {
    chip: string;
    dot: string;
    stripe: string;
    footer: string;
    text: string;
  }
> = {
  success: {
    chip: "border-primary/40 bg-primary/10 text-primary",
    dot: "bg-primary",
    stripe: "bg-primary/80",
    footer: "border-l-4 border-primary bg-primary/[0.04]",
    text: "text-primary",
  },
  warn: {
    chip: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
    stripe: "bg-amber-500/80",
    footer: "border-l-4 border-amber-500 bg-amber-500/[0.06]",
    text: "text-amber-700 dark:text-amber-300",
  },
  danger: {
    chip: "border-destructive/40 bg-destructive/10 text-destructive",
    dot: "bg-destructive",
    stripe: "bg-destructive/80",
    footer: "border-l-4 border-destructive bg-destructive/[0.06]",
    text: "text-destructive",
  },
  neutral: {
    chip: "border-border bg-muted/40 text-foreground",
    dot: "bg-muted-foreground",
    stripe: "bg-border",
    footer: "border-l-4 border-border bg-muted/[0.4]",
    text: "text-foreground",
  },
};

function statusTone(raw: string): StatusTone {
  const v = raw.toLowerCase();
  if (/(approve|post|ok|pass|success)/.test(v)) return "success";
  if (/(review|pending|hold|warn)/.test(v)) return "warn";
  if (/(fail|reject|block|error|denied)/.test(v)) return "danger";
  return "neutral";
}

function toneVerbForLabel(tone: StatusTone): string {
  switch (tone) {
    case "warn":
      return "Needs review";
    case "danger":
      return "Blocked";
    case "success":
      return "Approved";
    default:
      return "Status";
  }
}

// ─── value coercion ───────────────────────────────────────────────────────

function asString(v: unknown): string | undefined {
  if (v === null || v === undefined) return undefined;
  if (typeof v === "string") {
    const t = v.trim();
    return t.length === 0 ? undefined : t;
  }
  return String(v);
}

function asNumber(v: unknown): number | undefined {
  if (v === null || v === undefined || v === "") return undefined;
  const n = typeof v === "number" ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : undefined;
}

function coerceLineItems(raw: unknown): LineItem[] {
  if (!Array.isArray(raw)) return [];
  const items: LineItem[] = [];
  for (const entry of raw) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) continue;
    const obj = entry as Record<string, unknown>;
    items.push({
      description: asString(obj.description) ?? asString(obj.name) ?? "—",
      quantity: asNumber(obj.quantity) ?? asNumber(obj.qty) ?? 0,
      unit_price:
        asNumber(obj.unit_price) ??
        asNumber(obj.unitPrice) ??
        asNumber(obj.price) ??
        0,
      amount: asNumber(obj.amount) ?? asNumber(obj.total) ?? 0,
    });
  }
  return items;
}

// ─── formatting ───────────────────────────────────────────────────────────

const moneyFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatMoney(n: number): string {
  return moneyFormatter.format(n);
}

function formatDate(s: string | undefined): string | undefined {
  if (!s) return undefined;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ─── invoice-shape detector (exported for callers) ────────────────────────

/**
 * True when a JSON payload looks like an invoice — i.e. has the two fields
 * InvoiceHeroCard actually anchors on. Use this to branch a generic JSON
 * renderer into the hero treatment.
 */
export function isInvoiceShape(data: unknown): data is Record<string, unknown> {
  if (typeof data !== "object" || data === null || Array.isArray(data)) return false;
  const obj = data as Record<string, unknown>;
  return "vendor_name" in obj && "line_items" in obj && Array.isArray(obj.line_items);
}
