/**
 * MCP App user-intent extraction helper.
 *
 * The vendored MCP Apps spec defines the iframe → host return channel as
 * `ui/update-model-context` with a `structuredContent` payload. We layer
 * a fork-side convention on top: when `structuredContent` has the shape
 * `{ user_intent: { intent: string, source?: string, context?: object } }`,
 * the host interprets it as "the user wants to ask the agent this
 * question." See:
 *   docs/design/forks/gde-ap-agent/mcp-apps-interaction-pass.md
 *
 * This module owns the matching/extraction so every artefact host
 * (VendorKgPanel, APDashboardPanel) speaks the same wire format and the
 * page-level routing layer has one place to look for the spec.
 */

export interface UserIntentMessage {
  intent: string;
  source?: string;
  context?: Record<string, unknown>;
}

/**
 * Pattern-match an arbitrary `structuredContent` payload against the
 * `user_intent` convention. Returns null when the shape doesn't match
 * (so non-intent messages flow through callers unchanged).
 */
export function extractUserIntent(sc: Record<string, unknown>): UserIntentMessage | null {
  const raw = sc.user_intent;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const obj = raw as Record<string, unknown>;
  const intent = typeof obj.intent === "string" ? obj.intent.trim() : "";
  if (!intent) return null;
  const source = typeof obj.source === "string" ? obj.source : undefined;
  const context =
    obj.context && typeof obj.context === "object" && !Array.isArray(obj.context)
      ? (obj.context as Record<string, unknown>)
      : undefined;
  return { intent, source, context };
}
