"use client";

import Link from "next/link";
import type { Skill } from "@/types/skill";
import { SkillTab } from "./SkillTab";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BRANDING } from "@/lib/branding";
import { isAuditViewEnabled, type SpecialistKey } from "@/lib/auditViewFlag";
import { getSkillMeta } from "@/lib/skillMeta";
import { AuditViewBar } from "@/components/audit/AuditViewBar";
import type { SpecialistInvocations } from "@/hooks/useSpecialistInvocations";

interface SkillsBarProps {
  skills: Skill[];
  activeSkillId: string;
  isLoading: boolean;
  /** Kept for API compatibility — button is hidden from UI per competition design. */
  onCreateClick?: () => void;
  /** Audit-view state (set when isAuditViewEnabled()). Required for chip row. */
  invocations?: SpecialistInvocations;
  /** Open inspector key (set when isAuditViewEnabled()). */
  openInspectorKey?: SpecialistKey | null;
  /** Click handler for chips (set when isAuditViewEnabled()). */
  onChipSelect?: (key: SpecialistKey) => void;
}

export function SkillsBar({
  skills,
  activeSkillId,
  isLoading,
  invocations,
  openInspectorKey,
  onChipSelect,
}: SkillsBarProps) {
  const auditView = isAuditViewEnabled();

  // Hub-only filter: when audit view is on, only render the hub skill as a
  // navigable tab. Specialists become AuditViewBar chips.
  const tabSkills = auditView
    ? skills.filter((s) => {
        const meta = getSkillMeta(s);
        return meta?.role === "hub" || !meta; // unknown skills still render as tabs
      })
    : skills;

  return (
    <header
      className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4"
      aria-label="Skills navigation"
    >
      {/* Brand identity */}
      <Link href="/" className="flex shrink-0 items-center gap-2.5 mr-2" aria-label={BRANDING.appName}>
        <div className="relative flex h-9 w-9 shrink-0 items-center justify-center">
          <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={BRANDING.logo.chatAvatar}
            alt={BRANDING.appName}
            className="relative h-8 w-8 animate-glow-pulse"
          />
        </div>
        <span className="gradient-text-brand font-display hidden text-[13px] font-bold tracking-tight sm:inline">
          {BRANDING.appName}
        </span>
      </Link>

      <div className="h-5 w-px shrink-0 bg-border" />

      <nav
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
        style={{ scrollbarWidth: "none" }}
        data-testid="skill-tabs"
      >
        {isLoading ? (
          <SkillTabsSkeleton />
        ) : tabSkills.length === 0 ? (
          <span className="text-xs text-muted-foreground">Loading skills…</span>
        ) : (
          tabSkills.map((s) => (
            <SkillTab key={s.skillId} skill={s} active={s.skillId === activeSkillId} />
          ))
        )}

        {/* Audit-view chip row sits to the right of the hub tab.
            Visible only when the flag is on AND the invocations state was
            provided by the chat shell. */}
        {auditView && invocations && onChipSelect && (
          <>
            <div className="mx-2 h-5 w-px shrink-0 bg-border" aria-hidden="true" />
            <AuditViewBar
              invocations={invocations}
              openKey={openInspectorKey ?? null}
              onSelect={onChipSelect}
            />
          </>
        )}
      </nav>

      <ThemeToggle />
    </header>
  );
}

function SkillTabsSkeleton() {
  return (
    <div className="flex items-center gap-2" data-testid="skill-tabs-skeleton">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-7 w-24 animate-pulse rounded-full bg-muted" />
      ))}
    </div>
  );
}
