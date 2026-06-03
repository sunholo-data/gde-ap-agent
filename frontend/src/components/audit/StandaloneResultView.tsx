"use client";

import { A2UIRenderer } from "@/components/protocols/A2UIRenderer";
import { tryBuildFinalResponseCard } from "./finalResponseRender";
import { formatDuration, SectionLabel } from "./sharedView";
import { StandaloneToolCallCard } from "./StandaloneToolCallCard";

export interface StandaloneResult {
  /** Backend echoes the skill_id it ran; used here to namespace A2UI
   * fallback surface ids when the LLM forgot to emit createSurface. */
  skill_id?: string;
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
 * specialist directly. Designed so the agent's actual output (rendered
 * A2UI cards from the tool calls + a card built from the final response
 * JSON when applicable) is the first thing the user sees — not buried
 * behind a `<details>` summary like the v1 footer-only render, and not
 * dumped as escape-soup like the v2 raw-JSON render.
 */
export function StandaloneResultView({ result, onClear }: StandaloneResultViewProps) {
  const hasText = result.text.trim().length > 0;
  const toolCount = result.tool_calls.length;
  const skillId = result.skill_id ?? "standalone";
  const finalResponseCard = hasText
    ? tryBuildFinalResponseCard(result.text, skillId)
    : null;

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

      {/* Final assistant text — rendered as an A2UI card when JSON-only;
          falls back to <pre> for prose; placeholder for tool-only specialists. */}
      <div>
        <SectionLabel>Final response</SectionLabel>
        {hasText && finalResponseCard ? (
          <div className="mt-1 space-y-1.5">
            <div
              data-testid="audit-final-response-card"
              className="rounded border border-border bg-background p-2"
            >
              <A2UIRenderer
                messages={finalResponseCard}
                fallbackSurfaceId={`audit-final-${skillId}`}
              />
            </div>
            <details className="rounded border border-border bg-muted/20">
              <summary className="cursor-pointer select-none px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground">
                Raw text
              </summary>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap border-t border-border bg-background p-2 text-[11px] leading-relaxed text-foreground/85">
                {result.text}
              </pre>
            </details>
          </div>
        ) : hasText ? (
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

      {/* Tool calls — each rendered as a real A2UI card when the result is
          a send_a2ui_json_to_client envelope, with raw JSON tucked behind a
          disclosure. Non-A2UI tools fall back to InputOutputCard. */}
      {toolCount > 0 ? (
        <div>
          <SectionLabel>Tool calls (structured output)</SectionLabel>
          <ul className="mt-1 space-y-2">
            {result.tool_calls.map((tc, i) => (
              <li key={i}>
                <StandaloneToolCallCard
                  index={i + 1}
                  toolCall={tc}
                  skillId={skillId}
                />
              </li>
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
