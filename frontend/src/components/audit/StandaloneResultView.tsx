"use client";

import { cn } from "@/lib/utils";

export interface StandaloneResult {
  duration_ms: number;
  text: string;
  tool_calls: Array<{ name: string; args?: string; result?: unknown }>;
}

interface StandaloneResultViewProps {
  result: StandaloneResult;
  onClear: () => void;
}

/**
 * Prominent rendering of an Audit View "Run Standalone" result. Replaces
 * the EmptyState in the InspectorPanel body when the user runs a
 * specialist directly. Designed so the agent's actual output (tool
 * calls + their results) is the first thing the user sees — not buried
 * behind a `<details>` summary like the v1 footer-only render.
 */
export function StandaloneResultView({ result, onClear }: StandaloneResultViewProps) {
  const hasText = result.text.trim().length > 0;
  const toolCount = result.tool_calls.length;

  return (
    <section
      data-testid="audit-standalone-result"
      className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3"
    >
      {/* Header row */}
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-primary px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary-foreground">
            Standalone Result
          </span>
          <span className="text-[10px] font-medium text-muted-foreground">
            {formatDuration(result.duration_ms)} · {toolCount} tool call{toolCount === 1 ? "" : "s"}
          </span>
        </div>
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear standalone result"
          title="Clear and run again"
          className="shrink-0 rounded border border-border bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-foreground"
        >
          Clear
        </button>
      </header>

      {/* Final assistant text — usually empty for tool-only specialists like docparse */}
      <div>
        <SectionLabel>Final response</SectionLabel>
        {hasText ? (
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded border border-border bg-background p-2 text-[11px] leading-relaxed text-foreground/90">
            {result.text}
          </pre>
        ) : (
          <p className="mt-1 rounded border border-dashed border-border bg-background/50 px-2 py-1.5 text-[10px] italic text-muted-foreground">
            No narrative text — this specialist completed via tool calls only. See the structured
            outputs below.
          </p>
        )}
      </div>

      {/* Tool calls — expanded by default, with results */}
      {toolCount > 0 ? (
        <div>
          <SectionLabel>Tool calls (structured output)</SectionLabel>
          <ul className="mt-1 space-y-2">
            {result.tool_calls.map((tc, i) => (
              <ToolCallCard key={i} index={i + 1} tc={tc} />
            ))}
          </ul>
        </div>
      ) : (
        <p className="rounded border border-dashed border-border bg-background/50 px-2 py-1.5 text-[10px] italic text-muted-foreground">
          The specialist returned no tool calls. If you expected extracted fields, check that the
          input matched the schema and the agent had access to the tools it needed.
        </p>
      )}
    </section>
  );
}

function ToolCallCard({
  index,
  tc,
}: {
  index: number;
  tc: { name: string; args?: string; result?: unknown };
}) {
  const argsText = formatJsonish(tc.args);
  const resultText = formatJsonish(tc.result);
  return (
    <li className="overflow-hidden rounded border border-border bg-background">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/30 px-2 py-1">
        <span className="font-mono text-[11px] font-semibold text-primary">
          <span className="mr-1.5 inline-block min-w-[1.25rem] rounded bg-muted px-1 text-center text-[9px] text-muted-foreground">
            {index}
          </span>
          {tc.name || "(unnamed tool)"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 p-2 md:grid-cols-2">
        <div>
          <MicroLabel>Input</MicroLabel>
          {argsText ? (
            <pre className="mt-0.5 max-h-40 overflow-auto rounded border border-border bg-muted/30 p-1.5 text-[10px] leading-relaxed text-foreground/85">
              {argsText}
            </pre>
          ) : (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/60">(no args)</p>
          )}
        </div>
        <div>
          <MicroLabel>Output</MicroLabel>
          {resultText ? (
            <pre
              className={cn(
                "mt-0.5 max-h-40 overflow-auto rounded border p-1.5 text-[10px] leading-relaxed",
                "border-primary/20 bg-primary/5 text-foreground/90",
              )}
            >
              {resultText}
            </pre>
          ) : (
            <p className="mt-0.5 text-[10px] italic text-muted-foreground/60">
              (no result captured)
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/60">
      {children}
    </h3>
  );
}

function MicroLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/60">
      {children}
    </span>
  );
}

function formatDuration(ms: number): string {
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
function formatJsonish(value: unknown): string {
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
