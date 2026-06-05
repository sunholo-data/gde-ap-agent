"use client";

import { cn } from "@/lib/utils";
import { getMetaByKey } from "@/lib/skillMeta";
import type { SpecialistKey } from "@/lib/auditViewFlag";
import type { SpecialistState } from "@/hooks/useSpecialistInvocations";

interface SpecialistChipProps {
  specialistKey: SpecialistKey;
  state: SpecialistState;
  active: boolean;
  onClick: () => void;
}

/**
 * Audit-View chip — renders one specialist's live status in the top nav.
 * Clicking it opens the InspectorPanel for that specialist. NEVER navigates.
 *
 * State map:
 *   idle    → muted outline, no dot animation
 *   active  → pulsing primary dot, "running…" label
 *   done    → solid primary dot, latency badge (eg. "1.4s")
 *   error   → destructive dot, "error" label
 */
export function SpecialistChip({ specialistKey, state, active, onClick }: SpecialistChipProps) {
  // Map back to skillMeta key — chip key "validator" → meta key "validator",
  // chip key "poster" → meta key "poster". These already match.
  const meta = getMetaByKey(specialistKey);
  const { status, current } = state;

  const latencyMs =
    current && current.endedAt !== null && current.startedAt
      ? current.endedAt - current.startedAt
      : null;
  const latencyLabel = latencyMs !== null ? formatLatency(latencyMs) : null;

  return (
    <button
      type="button"
      onClick={onClick}
      title={`${meta.tagline} — ${meta.description}`}
      aria-pressed={active}
      data-testid={`audit-chip-${specialistKey}`}
      data-status={status}
      className={cn(
        "group inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-all duration-150",
        active
          ? "border-primary/50 bg-primary/10 text-primary shadow-[0_0_8px_rgba(232,168,0,0.2)]"
          : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground",
      )}
    >
      <StatusDot status={status} />
      <span className={cn("shrink-0", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground")}>
        {meta.icon}
      </span>
      <span className="max-w-[7rem] truncate">{meta.tagline}</span>
      {status === "done" && latencyLabel && (
        <span className="ml-0.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-primary animate-in fade-in zoom-in-95 duration-200">
          {latencyLabel}
        </span>
      )}
      {status === "active" && (
        <span className="ml-0.5 rounded-full bg-primary/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-primary animate-in fade-in zoom-in-95 duration-200">
          live
        </span>
      )}
      {status === "error" && (
        <span className="ml-0.5 rounded-full bg-destructive/20 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-destructive animate-in fade-in zoom-in-95 duration-200">
          err
        </span>
      )}
    </button>
  );
}

function StatusDot({ status }: { status: "idle" | "active" | "done" | "error" }) {
  if (status === "done") {
    return <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />;
  }
  if (status === "active") {
    return (
      <span className="relative flex h-2 w-2 shrink-0 items-center justify-center" aria-hidden="true">
        <span className="absolute h-2 w-2 animate-ping rounded-full bg-primary/40" />
        <span className="h-2 w-2 rounded-full bg-primary" />
      </span>
    );
  }
  if (status === "error") {
    return <span className="h-2 w-2 shrink-0 rounded-full bg-destructive" aria-hidden="true" />;
  }
  // idle
  return <span className="h-2 w-2 shrink-0 rounded-full border border-muted-foreground/40 bg-background" aria-hidden="true" />;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
