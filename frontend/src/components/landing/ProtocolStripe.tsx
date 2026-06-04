import Link from "next/link";
import { BRANDING } from "@/lib/branding";

/**
 * Horizontal stripe of the six tech pillars shown below the hero on the
 * landing page. AILANG sits first and gets the AILANG-family accent
 * (Sunholo red); the rest are industry protocols rendered in equal
 * neutral weight. Each tile deep-links to its anchor on /tech.
 */
export function ProtocolStripe() {
  return (
    <section className="border-y border-border bg-muted/20">
      <div className="mx-auto w-full max-w-7xl px-6 py-10 md:px-10">
        <div className="mb-6 flex items-end justify-between">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            Built on
          </h2>
          <Link
            href={BRANDING.demo.techHref}
            className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:text-primary"
          >
            See the full stack ↗
          </Link>
        </div>
        <ul className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3 lg:grid-cols-6">
          {BRANDING.demo.pillars.map((pillar) => (
            <li key={pillar.key} className="bg-background">
              <Link
                href={`${BRANDING.demo.techHref}#${pillar.key}`}
                className="group flex h-full flex-col gap-1 p-4 transition-colors hover:bg-muted/40"
              >
                <span
                  className={[
                    "font-display text-sm font-semibold tracking-tight",
                    pillar.key === "ailang"
                      ? "text-ailang"
                      : "text-foreground",
                  ].join(" ")}
                >
                  {pillar.label}
                </span>
                <span className="text-xs leading-snug text-muted-foreground">
                  {pillar.tagline}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
