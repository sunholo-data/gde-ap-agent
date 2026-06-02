"use client";

import { useState } from "react";

interface PosterVerdictFormProps {
  /** JSON string from the last validator run (sessionStorage). Used for
   * "Load from last validator" pre-fill — extracts invoice + reasons. */
  defaultValue: string | null;
  disabled?: boolean;
  onSubmit: (input: {
    verdict: "pass" | "needs_review";
    invoice: Record<string, unknown>;
    reasons?: unknown[];
  }) => void;
}

const EXAMPLE_INVOICE = {
  vendor_name: "Acme GmbH",
  invoice_number: "INV-2026-042",
  total: 8500,
  currency: "EUR",
};

/**
 * Hand-rolled form for the ap-poster audit run. Verdict radio + JSON
 * textarea for the invoice + reasons. No chat input.
 */
export function PosterVerdictForm({ defaultValue, disabled, onSubmit }: PosterVerdictFormProps) {
  const [verdict, setVerdict] = useState<"pass" | "needs_review">("pass");
  const [invoiceText, setInvoiceText] = useState<string>(() => extractInvoiceJson(defaultValue));
  const [reasonsText, setReasonsText] = useState<string>(() => extractReasonsJson(defaultValue));
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    let invoice: Record<string, unknown>;
    let reasons: unknown[] = [];
    try {
      invoice = JSON.parse(invoiceText);
    } catch (e) {
      setError(`Invoice JSON: ${e instanceof Error ? e.message : String(e)}`);
      return;
    }
    if (reasonsText.trim()) {
      try {
        const parsed = JSON.parse(reasonsText);
        if (!Array.isArray(parsed)) throw new Error("reasons must be an array");
        reasons = parsed;
      } catch (e) {
        setError(`Reasons JSON: ${e instanceof Error ? e.message : String(e)}`);
        return;
      }
    }
    onSubmit({ verdict, invoice, reasons });
  }

  function handleLoadLast() {
    if (!defaultValue) return;
    setInvoiceText(extractInvoiceJson(defaultValue));
    setReasonsText(extractReasonsJson(defaultValue));
    setError(null);
  }

  return (
    <form className="space-y-2" onSubmit={handleSubmit}>
      <div>
        <span className="block text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/70">
          Verdict
        </span>
        <div className="mt-1 flex gap-3">
          <label className="flex items-center gap-1.5 text-[11px]">
            <input
              type="radio"
              name="poster-verdict"
              checked={verdict === "pass"}
              onChange={() => setVerdict("pass")}
              disabled={disabled}
              className="accent-primary"
            />
            <span className="text-primary">pass</span>
            <span className="text-muted-foreground/60">(post to ERP)</span>
          </label>
          <label className="flex items-center gap-1.5 text-[11px]">
            <input
              type="radio"
              name="poster-verdict"
              checked={verdict === "needs_review"}
              onChange={() => setVerdict("needs_review")}
              disabled={disabled}
              className="accent-destructive"
            />
            <span className="text-destructive">needs_review</span>
            <span className="text-muted-foreground/60">(escalate)</span>
          </label>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/70">
          Invoice + reasons (JSON)
        </span>
        <button
          type="button"
          onClick={handleLoadLast}
          disabled={!defaultValue || disabled}
          className="rounded border border-border bg-background px-1.5 py-0.5 text-[9px] text-muted-foreground hover:border-primary/30 hover:text-foreground disabled:opacity-40"
          title={defaultValue ? "Pre-fill from the most recent validator output" : "No prior validator output in this session"}
        >
          Load last validator
        </button>
      </div>

      <label className="block text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60">Invoice</label>
      <textarea
        value={invoiceText}
        onChange={(e) => setInvoiceText(e.target.value)}
        rows={6}
        disabled={disabled}
        spellCheck={false}
        className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-[11px] leading-relaxed text-foreground focus:border-primary/40 focus:outline-none"
      />

      <label className="block text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60">Reasons (optional array)</label>
      <textarea
        value={reasonsText}
        onChange={(e) => setReasonsText(e.target.value)}
        rows={4}
        disabled={disabled}
        spellCheck={false}
        placeholder="[]"
        className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-[11px] leading-relaxed text-foreground focus:border-primary/40 focus:outline-none"
      />

      {error && <p className="text-[10px] text-destructive">{error}</p>}

      <button
        type="submit"
        disabled={disabled}
        className="rounded-lg bg-primary px-3 py-1.5 text-[11px] font-bold text-primary-foreground transition-all hover:shadow-[0_0_8px_rgba(232,168,0,0.3)] disabled:opacity-40 disabled:shadow-none"
      >
        Run Poster
      </button>
    </form>
  );
}

function extractInvoiceJson(raw: string | null): string {
  if (!raw) return JSON.stringify(EXAMPLE_INVOICE, null, 2);
  try {
    const parsed = JSON.parse(raw);
    // Validator output shape: {verdict, reasons, citations, invoice?}.
    // Prefer invoice key when present; otherwise pass the whole object
    // (audit users can edit).
    const candidate = parsed?.invoice ?? parsed;
    return JSON.stringify(candidate, null, 2);
  } catch {
    return raw;
  }
}

function extractReasonsJson(raw: string | null): string {
  if (!raw) return "[]";
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed?.reasons)) {
      return JSON.stringify(parsed.reasons, null, 2);
    }
    return "[]";
  } catch {
    return "[]";
  }
}
