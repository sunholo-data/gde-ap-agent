"use client";

import { JsonAsA2UICard } from "@/components/chat/JsonAsA2UICard";
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
  // Both Input and Output render as A2UI Cards via JsonAsA2UICard.
  // Replaces the prior `<pre>` raw-JSON dumps — the user-facing
  // promise of this app is "structured agent output → nicely-rendered
  // UI". Wherever the payload doesn't look like a renderable object
  // (eg. a plain tool-confirmation string) JsonAsA2UICard's muted
  // fallback shows the string so we still produce something useful.
  const hasInput = typeof input === "string" ? input.trim().length > 0 : input !== undefined;
  const hasOutput = output !== undefined && output !== null && (typeof output !== "string" || output.trim().length > 0);
  return (
    <div className={cn("overflow-hidden rounded border border-border bg-background", tone === "neutral" && "")}>
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
          {hasInput ? (
            <div className="mt-0.5">
              <JsonAsA2UICard
                value={input}
                fallbackTitle="Input"
                surfaceId={`audit-input-${title || index || "noid"}`}
                fallbackMessage="(no structured input)"
              />
            </div>
          ) : (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/60">(no input)</p>
          )}
        </div>
        <div>
          <MicroLabel>{outputLabel}</MicroLabel>
          {hasOutput ? (
            <div className="mt-0.5">
              <JsonAsA2UICard
                value={output}
                fallbackTitle="Output"
                surfaceId={`audit-output-${title || index || "noid"}`}
                fallbackMessage={emptyOutputMessage}
              />
            </div>
          ) : (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/60">{emptyOutputMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
}
