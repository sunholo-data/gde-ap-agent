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
        "flex h-9 shrink-0 items-center gap-2 border-b-2 px-3 text-sm transition-colors",
        active
          ? "border-primary font-medium text-foreground"
          : "border-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground",
      )}
    >
      {skill.avatar ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={skill.avatar} alt="" className="h-5 w-5 rounded-sm" />
      ) : null}
      <span className="max-w-[10rem] truncate">{name}</span>
    </Link>
  );
}
