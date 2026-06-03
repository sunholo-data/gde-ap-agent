// Audit-view helper for the "Final response" panel.
//
// The chat path turns a JSON-only assistant text into a styled A2UI Card via
// JsonCardBuilder so the user never sees a raw ```json fence. The audit view
// reuses the same conversion so the auditor sees the same rich card the
// end-user would have seen — not the escaped JSON the model literally
// emitted.

import { buildA2UICardFromJson } from "@/components/chat/JsonCardBuilder";
import { isLikelyJsonOnly } from "@/components/chat/MessageBubble";

const FENCE_RE = /^```(?:json)?\s*\n?([\s\S]*?)\n?```$/;

export function stripJsonFence(text: string): string {
  const trimmed = text.trim();
  const m = trimmed.match(FENCE_RE);
  return m ? m[1].trim() : trimmed;
}

export function tryBuildFinalResponseCard(
  text: string,
  fallbackTitle: string,
): Record<string, unknown>[] | null {
  const body = stripJsonFence(text);
  if (!isLikelyJsonOnly(body)) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return null;
  }
  return buildA2UICardFromJson(parsed, {
    fallbackTitle,
    surfaceId: "audit-final",
  });
}
