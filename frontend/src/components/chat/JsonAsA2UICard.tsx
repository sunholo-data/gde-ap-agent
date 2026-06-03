"use client";

// Render any JSON object as an inline A2UI Card via JsonCardBuilder.
//
// The user-facing promise of this app is "structured agent output →
// nicely-rendered UI". Wherever we currently show raw JSON (audit view,
// tool-call chips), wrap with this component so the user sees the same
// Card the workspace surface renders.
//
// Inputs accepted:
//   - A JSON string (parsed internally)
//   - An object/array (used directly)
//   - A stringified envelope (eg. ADK's tool-result ``{"result": "..."}``)
//     — we unwrap a single top-level ``result`` key when it's a string so
//     the model's plain-text confirmation doesn't render as ``"Result":
//     "..."`` field but is hidden in favour of the actual structured args.
//
// Fallback: when the input doesn't look like a renderable object (eg.
// a plain confirmation string, or empty input) we render a small muted
// preview of the raw value so the user still sees something useful.

import { A2UIRenderer } from "@/components/protocols/A2UIRenderer";
import { buildA2UICardFromJson } from "@/components/chat/JsonCardBuilder";
import { cn } from "@/lib/utils";

export interface JsonAsA2UICardProps {
  /** JSON object/array, or a string (parsed internally). */
  value: unknown;
  /** Title shown at the top of the Card when the JSON shape doesn't
   * suggest a better one. */
  fallbackTitle?: string;
  /** Unique surface id so the inline renderer doesn't collide with
   * other Cards rendered in the same view. */
  surfaceId?: string;
  /** Optional class for the outer wrapper. */
  className?: string;
  /** When the value can't be rendered as a Card (eg. it's just a plain
   * string), use this human-readable message in the muted fallback. */
  fallbackMessage?: string;
}

const ADK_TOOL_RESULT_WRAPPER_KEY = "result";

function parseInput(raw: unknown): unknown {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    try {
      return JSON.parse(trimmed);
    } catch {
      return raw;
    }
  }
  return raw;
}

/** Unwrap ADK's tool-result envelope when it's a single-string ``result``
 * field (the typical shape for ``return "Emitted ap_invoice for..."``).
 * Returning the inner string lets the fallback branch render a muted
 * preview instead of a Card with one row. */
function unwrapAdkToolResult(value: unknown): unknown {
  if (value === null || value !== Object(value) || Array.isArray(value)) return value;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);
  if (keys.length === 1 && keys[0] === ADK_TOOL_RESULT_WRAPPER_KEY) {
    return obj[ADK_TOOL_RESULT_WRAPPER_KEY];
  }
  return value;
}

export function JsonAsA2UICard({
  value,
  fallbackTitle = "Result",
  surfaceId,
  className,
  fallbackMessage,
}: JsonAsA2UICardProps) {
  const parsed = unwrapAdkToolResult(parseInput(value));

  const safeSurfaceId =
    surfaceId ??
    `json-card-${Math.random().toString(36).slice(2, 10)}`;

  const messages =
    parsed !== null && typeof parsed === "object"
      ? buildA2UICardFromJson(parsed, { fallbackTitle, surfaceId: safeSurfaceId })
      : null;

  if (messages && messages.length > 0) {
    return (
      <div className={className}>
        <A2UIRenderer
          messages={messages}
          fallbackSurfaceId={safeSurfaceId}
          onAction={() => {
            // JsonAsA2UICard Cards are read-only — clicks on any
            // generated component (none today) are intentionally
            // no-op. Wire up onAction if a fork adds buttons.
          }}
        />
      </div>
    );
  }

  // Fallback — plain string or empty value. Show a small muted
  // preview so the user always sees something, never a raw blob.
  const text = typeof parsed === "string" ? parsed : JSON.stringify(parsed ?? "");
  return (
    <div
      className={cn(
        "rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] italic text-muted-foreground",
        className,
      )}
    >
      {text || fallbackMessage || "(no structured output)"}
    </div>
  );
}
