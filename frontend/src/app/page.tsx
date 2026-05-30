import { BackendHealthBadge } from "@/components/BackendHealthBadge";
import { MySkillsButton } from "@/components/MySkillsButton";
import { SignInButton } from "@/components/SignInButton";
import { skillHref } from "@/components/navigation/skillHref";
import { BRANDING } from "@/lib/branding";
import Link from "next/link";

const SHOW_DEV_PROBES = process.env.NEXT_PUBLIC_SHOW_DEV_PROBES === "true";

interface SkillSummary {
  skillId: string;
  ownerId: string;
  slug: string | null;
  name: string;
  description: string;
}

async function getMarketplaceSkills(): Promise<SkillSummary[]> {
  try {
    const backendUrl =
      process.env.BACKEND_URL ?? "http://localhost:1956";
    const res = await fetch(`${backendUrl}/api/skills/marketplace?limit=10`, {
      next: { revalidate: 30 },
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function HomePage() {
  const skills = await getMarketplaceSkills();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="flex flex-col items-center gap-6 max-w-2xl text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={BRANDING.logo.heroAnimated}
          alt={BRANDING.appName}
          className="w-32 h-32"
        />
        <h1 className="text-4xl font-semibold tracking-tight">
          {BRANDING.appName}
        </h1>
        <p className="text-muted-foreground text-lg">{BRANDING.tagline}</p>
        <SignInButton />
        <BackendHealthBadge />
        {SHOW_DEV_PROBES && <MySkillsButton />}

        {skills.length > 0 && (
          <div className="w-full mt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3">
              Public skills
            </p>
            <ul className="flex flex-col gap-2 w-full">
              {skills.map((skill) => (
                <li key={skill.skillId}>
                  <Link
                    href={skillHref(skill)}
                    className="flex flex-col items-start px-4 py-3 rounded-lg border border-border hover:bg-accent transition-colors text-left w-full"
                  >
                    <span className="font-medium text-sm">{skill.name}</span>
                    {skill.description && (
                      <span className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                        {skill.description}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}
