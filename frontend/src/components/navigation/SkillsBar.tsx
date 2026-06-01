"use client";

import Link from "next/link";
import type { Skill } from "@/types/skill";
import { SkillTab } from "./SkillTab";
import { BRANDING } from "@/lib/branding";

interface SkillsBarProps {
  skills: Skill[];
  activeSkillId: string;
  isLoading: boolean;
  onCreateClick: () => void;
}

export function SkillsBar({ skills, activeSkillId, isLoading, onCreateClick }: SkillsBarProps) {
  return (
    <header
      className="flex h-14 shrink-0 items-center gap-3 border-b border-white/[0.07] bg-[hsl(222,47%,4%)] px-4"
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

      <div className="h-5 w-px shrink-0 bg-white/[0.08]" />

      <nav
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
        style={{ scrollbarWidth: "none" }}
        data-testid="skill-tabs"
      >
        {isLoading ? (
          <SkillTabsSkeleton />
        ) : skills.length === 0 ? (
          <span className="text-xs text-muted-foreground">No skills — create one →</span>
        ) : (
          skills.map((s) => (
            <SkillTab key={s.skillId} skill={s} active={s.skillId === activeSkillId} />
          ))
        )}
      </nav>

      <button
        type="button"
        onClick={onCreateClick}
        title="Create a new skill"
        aria-label="Create a new skill"
        className="flex shrink-0 items-center gap-1.5 rounded-full border border-primary/25 bg-primary/8 px-3 py-1.5 text-xs font-semibold text-primary transition-all hover:bg-primary/18 hover:border-primary/40"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M8 3v10M3 8h10" strokeLinecap="round" />
        </svg>
        New
      </button>
    </header>
  );
}

function SkillTabsSkeleton() {
  return (
    <div className="flex items-center gap-2" data-testid="skill-tabs-skeleton">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-7 w-24 animate-pulse rounded-full bg-white/[0.06]" />
      ))}
    </div>
  );
}
