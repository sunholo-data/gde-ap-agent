/**
 * Audit View UX flag.
 *
 * Defaults ON. Set NEXT_PUBLIC_INSPECTOR_UX=0 to revert to the legacy
 * four-peer-tab layout (orchestrator + 3 specialist tabs).
 *
 * See docs/design/forks/gde-ap-agent/multi-agent-inspector-ux.md
 */
export function isAuditViewEnabled(): boolean {
  return process.env.NEXT_PUBLIC_INSPECTOR_UX !== "0";
}

/** Specialist keys recognised by the audit-view layer.
 *
 * Match the matchKey() output in skillMeta.tsx — kept here as a separate
 * constant so other modules (chip reducer, inspector panel) can iterate
 * without re-deriving from skill list.
 */
export const SPECIALIST_KEYS = ["docparse", "validator", "poster"] as const;
export type SpecialistKey = (typeof SPECIALIST_KEYS)[number];

/** Tool-call name → specialist key. Matches the trigger lists in
 * APPipelineSteps so the chip and pipeline stay in sync.
 */
export function specialistKeyForToolName(name: string): SpecialistKey | null {
  const n = name.toLowerCase();
  if (n.includes("docparse")) return "docparse";
  if (n.includes("ap_validator") || n.includes("ap-validator") || n.includes("validator")) return "validator";
  if (n.includes("ap_poster") || n.includes("ap-poster") || n.includes("poster")) return "poster";
  return null;
}
