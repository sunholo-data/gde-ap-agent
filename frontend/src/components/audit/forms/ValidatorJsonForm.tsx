"use client";

import { useEffect, useState } from "react";

interface ValidatorJsonFormProps {
  /** JSON string from the last docparse run (sessionStorage). Used for
   * the "Load from last docparse" pre-fill. */
  defaultValue: string | null;
  disabled?: boolean;
  onSubmit: (input: Record<string, unknown>) => void;
}

const EXAMPLE_INVOICE = {
  vendor_name: "Acme GmbH",
  vendor_id: "V-1042",
  invoice_number: "INV-2026-042",
  invoice_date: "2026-05-15",
  due_date: "2026-06-14",
  po_reference: "PO-77820",
  currency: "EUR",
  line_items: [
    { description: "Consulting services — May", quantity: 1, unit_price: 8500, amount: 8500 },
  ],
  subtotal: 8500,
  tax: 0,
  total: 8500,
};

/**
 * Hand-rolled JSON form for the ap-validator audit run. No chat box —
 * structured input only. The textarea is JSON.parse-validated on blur
 * (no Monaco; keeps bundle slim).
 */
export function ValidatorJsonForm({ defaultValue, disabled, onSubmit }: ValidatorJsonFormProps) {
  const [text, setText] = useState<string>(() => prettyOrExample(defaultValue));
  const [parseError, setParseError] = useState<string | null>(null);

  // If sessionStorage gets a fresh "last docparse" mid-session, update on next form open.
  useEffect(() => {
    if (defaultValue && text === "") setText(prettyOrExample(defaultValue));
  }, [defaultValue, text]);

  function handleBlur() {
    setParseError(parseCheck(text));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const err = parseCheck(text);
    setParseError(err);
    if (err) return;
    try {
      onSubmit(JSON.parse(text) as Record<string, unknown>);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : String(e));
    }
  }

  function handleLoadLast() {
    if (defaultValue) setText(prettyOrExample(defaultValue));
  }

  function handleLoadExample() {
    setText(JSON.stringify(EXAMPLE_INVOICE, null, 2));
    setParseError(null);
  }

  return (
    <form className="space-y-2" onSubmit={handleSubmit}>
      <div className="flex items-center justify-between">
        <label
          htmlFor="validator-json"
          className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/70"
        >
          Invoice JSON
        </label>
        <div className="flex gap-1">
          <button
            type="button"
            disabled={!defaultValue || disabled}
            onClick={handleLoadLast}
            className="rounded border border-border bg-background px-1.5 py-0.5 text-[9px] text-muted-foreground hover:border-primary/30 hover:text-foreground disabled:opacity-40"
            title={defaultValue ? "Pre-fill with the most recent docparse output" : "No prior docparse output in this session"}
          >
            Load last docparse
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={handleLoadExample}
            className="rounded border border-border bg-background px-1.5 py-0.5 text-[9px] text-muted-foreground hover:border-primary/30 hover:text-foreground disabled:opacity-40"
          >
            Example
          </button>
        </div>
      </div>
      <textarea
        id="validator-json"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={handleBlur}
        rows={10}
        disabled={disabled}
        spellCheck={false}
        className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-[11px] leading-relaxed text-foreground focus:border-primary/40 focus:outline-none"
      />
      {parseError && (
        <p className="text-[10px] text-destructive">{parseError}</p>
      )}
      <button
        type="submit"
        disabled={disabled || !!parseError}
        className="rounded-lg bg-primary px-3 py-1.5 text-[11px] font-bold text-primary-foreground transition-all hover:shadow-[0_0_8px_rgba(232,168,0,0.3)] disabled:opacity-40 disabled:shadow-none"
      >
        Run Validator
      </button>
    </form>
  );
}

function prettyOrExample(raw: string | null): string {
  if (!raw) return JSON.stringify(EXAMPLE_INVOICE, null, 2);
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function parseCheck(text: string): string | null {
  if (!text.trim()) return "Empty input";
  try {
    JSON.parse(text);
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}
