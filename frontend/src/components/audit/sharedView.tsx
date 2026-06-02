"use client";

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
 */
export function formatJsonish(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "";
    try {
      return JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      return trimmed;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
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
  const inputText = formatJsonish(input);
  const outputText = formatJsonish(output);
  return (
    <div className="overflow-hidden rounded border border-border bg-background">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/30 px-2 py-1">
        <span className="font-mono text-[11px] font-semibold text-primary">
          {index !== undefined && (
            <span className="mr-1.5 inline-block min-w-[1.25rem] rounded bg-muted px-1 text-center text-[9px] text-muted-foreground">
              {index}
            </span>
          )}
          {title || "(unnamed)"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 p-2 md:grid-cols-2">
        <div>
          <MicroLabel>{inputLabel}</MicroLabel>
          {inputText ? (
            <pre className="mt-0.5 max-h-40 overflow-auto rounded border border-border bg-muted/30 p-1.5 text-[10px] leading-relaxed text-foreground/85">
              {inputText}
            </pre>
          ) : (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/60">(no input)</p>
          )}
        </div>
        <div>
          <MicroLabel>{outputLabel}</MicroLabel>
          {outputText ? (
            <pre
              className={cn(
                "mt-0.5 max-h-40 overflow-auto rounded border p-1.5 text-[10px] leading-relaxed",
                tone === "primary"
                  ? "border-primary/20 bg-primary/5 text-foreground/90"
                  : "border-border bg-muted/30 text-foreground/85",
              )}
            >
              {outputText}
            </pre>
          ) : (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/60">{emptyOutputMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
}
