"use client";

import Link from "next/link";
import type { Skill } from "@/types/skill";
import { cn } from "@/lib/utils";
import { getSkillMeta } from "@/lib/skillMeta";
import { skillHref } from "./skillHref";

interface SkillTabProps {
  skill: Skill;
  active: boolean;
}

export function SkillTab({ skill, active }: SkillTabProps) {
  const meta = getSkillMeta(skill);
  const name = meta?.tagline ?? skill.displayName ?? skill.name ?? skill.skillId.slice(0, 8);
  const tooltip = meta ? `${name}\n${meta.description}` : name;

  return (
    <Link
      href={skillHref(skill)}
      title={tooltip}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-xs font-medium transition-all duration-150",
        active
          ? "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(232,168,0,0.25)]"
          : "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground dark:hover:bg-white/[0.06]",
      )}
    >
      {/* Skill icon from skillMeta, or fallback avatar */}
      {meta ? (
        <span className={cn("shrink-0", active ? "text-primary-foreground" : "text-muted-foreground group-hover:text-foreground")}>
          {meta.icon}
        </span>
      ) : skill.avatar ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={skill.avatar} alt="" className="h-4 w-4 rounded-sm" />
      ) : null}

      <span className="max-w-[9rem] truncate">{name}</span>

      {/* Entry-point badge */}
      {meta?.isEntryPoint && (
        <span
          className={cn(
            "hidden shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider sm:inline-block",
            active
              ? "bg-primary-foreground/20 text-primary-foreground"
              : "bg-primary/15 text-primary",
          )}
        >
          Hub
        </span>
      )}
    </Link>
  );
}
