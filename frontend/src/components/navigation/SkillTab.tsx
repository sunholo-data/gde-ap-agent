"use client";

import Link from "next/link";
import type { Skill } from "@/types/skill";
import { cn } from "@/lib/utils";
import { skillHref } from "./skillHref";

interface SkillTabProps {
  skill: Skill;
  active: boolean;
}

export function SkillTab({ skill, active }: SkillTabProps) {
  const name = skill.displayName || skill.name || skill.skillId.slice(0, 8);
  return (
    <Link
      href={skillHref(skill)}
      title={name}
      aria-current={active ? "page" : undefined}
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-xs font-medium transition-all duration-150",
        active
          ? "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(232,168,0,0.25)]"
          : "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground",
      )}
    >
      {skill.avatar ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={skill.avatar} alt="" className="h-4 w-4 rounded-sm" />
      ) : null}
      <span className="max-w-[9rem] truncate">{name}</span>
    </Link>
  );
}
