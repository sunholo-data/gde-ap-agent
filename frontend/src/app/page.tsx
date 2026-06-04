import Image from "next/image";
import Link from "next/link";
import { BackendHealthBadge } from "@/components/BackendHealthBadge";
import { BrandFooter } from "@/components/BrandFooter";
import { MySkillsButton } from "@/components/MySkillsButton";
import { SignInButton } from "@/components/SignInButton";
import { APHero } from "@/components/landing/APHero";
import { ProtocolStripe } from "@/components/landing/ProtocolStripe";
import { DemoSteps } from "@/components/landing/DemoSteps";
import { BRANDING } from "@/lib/branding";

const SHOW_DEV_PROBES = process.env.NEXT_PUBLIC_SHOW_DEV_PROBES === "true";

/**
 * Landing — pure AP showcase.
 *
 * The previous version of this page rendered a generic marketplace list
 * of public skills via /api/skills/marketplace. For the GfS AI Agents
 * Challenge submission, every visitor is funnelled into ONE flow: the
 * ap-orchestrator chat. The marketplace pattern was distracting and the
 * skills it surfaced were largely irrelevant to the AP demo story.
 */
export default function HomePage() {
  return (
    <main className="relative flex min-h-screen flex-col">
      {/* Top chrome — logo, sign-in, dev probes. Sits over the hero, no
          background plate of its own so the page reads as one composition. */}
      <header className="absolute inset-x-0 top-0 z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 md:px-10">
        <Link
          href="/"
          className="flex items-center gap-2.5"
          aria-label={BRANDING.appName}
        >
          <Image
            src={BRANDING.logo.heroAnimated}
            alt=""
            width={32}
            height={32}
            className="h-8 w-8"
            priority
          />
          <span className="hidden font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground sm:inline">
            ailang-parse · AP Showcase
          </span>
        </Link>
        <nav className="flex items-center gap-2">
          <Link
            href={BRANDING.demo.techHref}
            className="hidden rounded-md px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground sm:inline-flex"
          >
            Tech stack
          </Link>
          <SignInButton />
          <BackendHealthBadge />
          {SHOW_DEV_PROBES && <MySkillsButton />}
        </nav>
      </header>

      <APHero />
      <ProtocolStripe />
      <DemoSteps />

      <BrandFooter />
    </main>
  );
}
