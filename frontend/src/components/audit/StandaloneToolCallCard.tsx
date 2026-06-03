"use client";

import { parseA2UIResult } from "@/components/chat/MessageBubble";
import { A2UIRenderer } from "@/components/protocols/A2UIRenderer";
import { InputOutputCard, MicroLabel } from "./sharedView";

/**
 * Audit-view rendering of a single tool call from a Run-Standalone result.
 *
 * Decision tree:
 *  - Result parses as the `send_a2ui_json_to_client` envelope → render the
 *    validated message array via A2UIRenderer (the same component the chat
 *    bubble uses), with the raw input/output JSON tucked behind a disclosure.
 *  - Tool was `send_a2ui_json_to_client` but the envelope didn't parse → the
 *    SDK returned an error envelope. Show the error inline with the raw
 *    disclosure still present.
 *  - Anything else (transfer_to_*, FS tools, etc.) → fall back to the classic
 *    InputOutputCard so non-A2UI tool calls render exactly as before.
 *
 * Routed-surface hints (surface_id / update_mode) are intentionally ignored:
 * audit view always renders inline, even for tool calls that would have been
 * routed to workspace/sidebar in a live session.
 */
export function StandaloneToolCallCard({
  index,
  toolCall,
  skillId,
}: {
  index: number;
  toolCall: { name: string; args?: string; result?: unknown };
  skillId: string;
}) {
  const resultString =
    typeof toolCall.result === "string"
      ? toolCall.result
      : toolCall.result === undefined || toolCall.result === null
        ? undefined
        : JSON.stringify(toolCall.result);

  const parsed = parseA2UIResult(resultString);

  if (parsed) {
    return (
      <CardShell index={index} title={toolCall.name}>
        <div className="rounded border border-primary/20 bg-background p-2">
          <A2UIRenderer
            messages={parsed.messages}
            fallbackSurfaceId={`audit-${skillId}-${index}`}
          />
        </div>
        <RawJsonDisclosure
          input={toolCall.args}
          output={toolCall.result}
        />
      </CardShell>
    );
  }

  if (toolCall.name === "send_a2ui_json_to_client") {
    const errorMessage = extractErrorMessage(toolCall.result);
    return (
      <CardShell index={index} title={toolCall.name}>
        <div className="rounded border border-destructive/40 bg-destructive/5 p-2 text-[11px] text-destructive">
          <div className="mb-1 font-semibold uppercase tracking-wider">
            A2UI validation failed
          </div>
          {errorMessage ? (
            <pre className="whitespace-pre-wrap leading-relaxed">
              {errorMessage}
            </pre>
          ) : (
            <p className="italic text-destructive/80">
              No error message captured.
            </p>
          )}
        </div>
        <RawJsonDisclosure
          input={toolCall.args}
          output={toolCall.result}
        />
      </CardShell>
    );
  }

  return (
    <InputOutputCard
      index={index}
      title={toolCall.name}
      input={toolCall.args}
      output={toolCall.result}
    />
  );
}

function CardShell({
  index,
  title,
  children,
}: {
  index: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded border border-border bg-background">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/30 px-2 py-1">
        <span className="font-mono text-[11px] font-semibold text-primary">
          <span className="mr-1.5 inline-block min-w-[1.25rem] rounded bg-muted px-1 text-center text-[9px] text-muted-foreground">
            {index}
          </span>
          {title || "(unnamed)"}
        </span>
      </div>
      <div className="space-y-2 p-2">{children}</div>
    </div>
  );
}

function RawJsonDisclosure({
  input,
  output,
}: {
  input?: string;
  output?: unknown;
}) {
  return (
    <details className="group rounded border border-border bg-muted/20">
      <summary className="cursor-pointer select-none px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground">
        Raw JSON
      </summary>
      <div className="border-t border-border p-2">
        <InputOutputCard
          title=""
          input={input}
          output={output}
          tone="neutral"
        />
        {/* Keep a MicroLabel-style hint near the bottom to remind auditors
            that the rendered card above is the source of truth. */}
        <p className="mt-1.5 text-[9px] italic text-muted-foreground/60">
          <MicroLabel>For audit only</MicroLabel> — the rendered card above is
          what end-users see.
        </p>
      </div>
    </details>
  );
}

function extractErrorMessage(result: unknown): string | null {
  if (result == null) return null;
  let obj: unknown = result;
  if (typeof obj === "string") {
    try {
      obj = JSON.parse(obj);
    } catch {
      return obj as string;
    }
  }
  if (typeof obj !== "object" || obj === null) return null;
  const r = obj as Record<string, unknown>;
  const parts: string[] = [];
  if (typeof r.error === "string") parts.push(r.error);
  if (typeof r.message === "string") parts.push(r.message);
  return parts.length > 0 ? parts.join("\n\n") : null;
}
