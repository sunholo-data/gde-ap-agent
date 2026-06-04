"use client";

import { JsonAsStructuredCard } from "@/components/chat/JsonAsStructuredCard";
import { cn } from "@/lib/utils";

/**
 * Shared rendering primitives for Audit View output panels.
 *
 * Both StandaloneResultView (Run-Standalone) and InvocationBody
 * (orchestrator-driven) use these so the user gets a consistent
 * "Input on the left, Output on the right, pretty-printed JSON, no
 * collapsed disclosures" layout no matter how the specialist was
 * invoked.
 */

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/60">
      {children}
    </h3>
  );
}

export function MicroLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60">
      {children}
    </span>
  );
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

/**
 * Pretty-print whatever the backend gave us. Handles:
 *  - JSON strings (parse + indent)
 *  - already-parsed objects (stringify)
 *  - plain strings (return as-is, trimmed)
 *  - null/undefined → empty string
 *
 * Recursively unwraps string values that themselves contain JSON (depth-
 * capped at 4). This matters for the `send_a2ui_json_to_client` input
 * `{ "a2ui_json": "[escaped JSON]" }` — without the unwrap the auditor's
 * Raw JSON disclosure shows escape-soup instead of the nested array.
 */
export function formatJsonish(value: unknown): string {
  if (value == null) return "";
  let parsed: unknown;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "";
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  } else {
    parsed = value;
  }
  try {
    return JSON.stringify(deepUnwrapJson(parsed), null, 2);
  } catch {
    return String(value);
  }
}

function looksLikeJson(s: string): boolean {
  if (s.length === 0) return false;
  const c = s[0];
  return c === "{" || c === "[" || c === '"';
}

function deepUnwrapJson(value: unknown, depth = 0): unknown {
  if (depth > 4) return value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!looksLikeJson(trimmed)) return value;
    try {
      return deepUnwrapJson(JSON.parse(trimmed), depth + 1);
    } catch {
      return value;
    }
  }
  if (Array.isArray(value)) {
    return value.map((v) => deepUnwrapJson(v, depth + 1));
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = deepUnwrapJson(v, depth + 1);
    }
    return out;
  }
  return value;
}

/**
 * Rich card showing one input/output pair side-by-side. Used by both
 * the standalone tool-calls list and the orchestrator-driven view.
 *
 * `index` is optional — pass a 1-based ordinal when rendering a list,
 * omit for a single-card view (eg. orchestrator's transfer_to_X call).
 * `tone` shifts the Output column's accent: "primary" (default) for
 * specialist results, "neutral" for raw tool calls.
 */
export function InputOutputCard({
  title,
  input,
  output,
  index,
  tone = "primary",
  inputLabel = "Input",
  outputLabel = "Output",
  emptyOutputMessage = "(no result captured)",
}: {
  title: string;
  input?: string;
  output?: unknown;
  index?: number;
  tone?: "primary" | "neutral";
  inputLabel?: string;
  outputLabel?: string;
  emptyOutputMessage?: string;
}) {
  // Stacked layout (was side-by-side two-column). The earlier grid-cols-2
  // squeezed input/output into ~250px each in a 480px right panel, which
  // forced A2UI Row's labels ("Po Reference", "Invoice Number") to wrap.
  // Stacking restores full width to each panel and lets JsonAsStructuredCard
  // render with a proper fixed-width-label DefinitionList layout.
  const hasInput = typeof input === "string" ? input.trim().length > 0 : input !== undefined;
  const hasOutput = output !== undefined && output !== null && (typeof output !== "string" || output.trim().length > 0);
  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border bg-background",
        tone === "neutral" && "",
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border bg-muted/20 px-4 py-2.5">
        <span className="flex items-center gap-2">
          {index !== undefined && (
            <span className="inline-block min-w-[1.25rem] rounded bg-primary/10 px-1.5 py-0.5 text-center font-mono text-[10px] font-semibold tabular-nums text-primary">
              {index}
            </span>
          )}
          <span className="font-display text-sm font-semibold tracking-tight text-foreground">
            {title || "(unnamed)"}
          </span>
        </span>
      </header>
      <div className="space-y-4 p-4">
        <div>
          <MicroLabel>{inputLabel}</MicroLabel>
          <div className="mt-2">
            {hasInput ? (
              <JsonAsStructuredCard value={input} fallbackTitle="Input" />
            ) : (
              <p className="text-xs italic text-muted-foreground">(no input)</p>
            )}
          </div>
        </div>
        <div className="h-px bg-border" />
        <div>
          <MicroLabel>{outputLabel}</MicroLabel>
          <div className="mt-2">
            {hasOutput ? (
              <JsonAsStructuredCard
                value={output}
                fallbackTitle="Output"
                fallbackMessage={emptyOutputMessage}
              />
            ) : (
              <p className="text-xs italic text-muted-foreground">{emptyOutputMessage}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
