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
 *
 * Three historical naming layers are matched:
 *   1. ``transfer_to_<specialist>`` — original orchestrator pattern (pre-M1
 *      SequentialAgent refactor).
 *   2. ``docparse`` — legacy name for the extractor; preserved so older
 *      sessions still light up.
 *   3. ``emit_<specialist_output>`` — function-as-schema emit tools added
 *      in the AP-pipeline refactor. These are the PRIMARY signal post-M1
 *      because each specialist calls its emit tool exactly once at end
 *      of turn with the structured output; ``resultContent`` carries the
 *      confirmation string and ``argsJson`` carries the validated payload
 *      the inspector wants to display.
 */
export function specialistKeyForToolName(name: string): SpecialistKey | null {
  const n = name.toLowerCase();
  if (
    n.includes("invoice_extractor") ||
    n.includes("invoice-extractor") ||
    n.includes("docparse") ||
    n === "emit_invoice_extraction"
  ) {
    return "docparse";
  }
  if (
    n.includes("ap_validator") ||
    n.includes("ap-validator") ||
    n.includes("validator") ||
    n === "emit_ap_verdict"
  ) {
    return "validator";
  }
  if (
    n.includes("ap_poster") ||
    n.includes("ap-poster") ||
    n.includes("poster") ||
    n === "emit_posting_record"
  ) {
    return "poster";
  }
  return null;
}
