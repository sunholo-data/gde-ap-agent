"use client";

import Link from "next/link";
import type { Skill } from "@/types/skill";
import { SkillTab } from "./SkillTab";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BRANDING } from "@/lib/branding";

interface SkillsBarProps {
  skills: Skill[];
  activeSkillId: string;
  isLoading: boolean;
  /** Kept for API compatibility — button is hidden from UI per competition design. */
  onCreateClick?: () => void;
}

export function SkillsBar({ skills, activeSkillId, isLoading }: SkillsBarProps) {
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
        <div className="hidden flex-col leading-none sm:flex">
          <span className="gradient-text-gold text-[13px] font-bold tracking-tight">
            {BRANDING.appName}
          </span>
          <span className="mt-0.5 text-[10px] text-primary/60">
            {BRANDING.tagline}
          </span>
        </div>
      </Link>

      <div className="h-5 w-px shrink-0 bg-border" />

      {/* Agent-chain badge — explains the multi-agent AP pipeline */}
      <div className="hidden items-center gap-1.5 lg:flex shrink-0">
        <span className="rounded-full border border-primary/20 bg-primary/8 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-primary/70">
          4 Agents
        </span>
        <span className="rounded-full border border-emerald-500/20 bg-emerald-500/8 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-emerald-400/70">
          Live
        </span>
      </div>

      <nav
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
        style={{ scrollbarWidth: "none" }}
        data-testid="skill-tabs"
      >
        {isLoading ? (
          <SkillTabsSkeleton />
        ) : skills.length === 0 ? (
          <span className="text-xs text-muted-foreground">Loading skills…</span>
        ) : (
          skills.map((s) => (
            <SkillTab key={s.skillId} skill={s} active={s.skillId === activeSkillId} />
          ))
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
