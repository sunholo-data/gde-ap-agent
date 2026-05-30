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
      className="flex h-12 items-center gap-2 border-b bg-background px-3"
      aria-label="Skills navigation"
    >
      <Link href="/" className="flex shrink-0 items-center" aria-label="Home">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={BRANDING.logo.chatAvatar}
          alt={BRANDING.appName}
          className="h-7 w-7"
        />
      </Link>

      <nav className="flex min-w-0 flex-1 items-center gap-0 overflow-x-auto" data-testid="skill-tabs">
        {isLoading ? (
          <SkillTabsSkeleton />
        ) : skills.length === 0 ? (
          <span className="text-xs text-muted-foreground">No skills yet — create your first one →</span>
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
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-lg leading-none text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        +
      </button>
    </header>
  );
}

function SkillTabsSkeleton() {
  return (
    <div className="flex items-center gap-2" data-testid="skill-tabs-skeleton">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-6 w-24 animate-pulse rounded bg-muted" />
      ))}
    </div>
  );
}
