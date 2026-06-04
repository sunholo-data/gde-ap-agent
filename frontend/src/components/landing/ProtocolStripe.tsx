import Link from "next/link";
import { BRANDING } from "@/lib/branding";
import { ProtocolIcon } from "@/components/tech/ProtocolIcon";

/**
 * Horizontal stripe of the six tech pillars shown below the hero on the
 * landing page. AILANG sits first and gets the AILANG-family accent
 * (Sunholo red); the rest are industry protocols rendered in equal
 * neutral weight. Each tile carries an inline glyph and deep-links to
 * its anchor on /tech; a small "spec ↗" link goes to the canonical
 * external docs without leaving the deep-link primary action.
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
          {BRANDING.demo.pillars.map((pillar) => {
            const isAilang = pillar.key === "ailang";
            return (
              <li key={pillar.key} className="relative bg-background">
                <Link
                  href={`${BRANDING.demo.techHref}#${pillar.key}`}
                  className="group flex h-full flex-col gap-2 p-4 transition-colors hover:bg-muted/40"
                >
                  <ProtocolIcon
                    pillar={pillar.key as Parameters<typeof ProtocolIcon>[0]["pillar"]}
                    className={[
                      "h-5 w-5 transition-colors",
                      isAilang
                        ? "text-ailang"
                        : "text-muted-foreground group-hover:text-primary",
                    ].join(" ")}
                  />
                  <span
                    className={[
                      "font-display text-sm font-semibold tracking-tight",
                      isAilang ? "text-ailang" : "text-foreground",
                    ].join(" ")}
                  >
                    {pillar.label}
                  </span>
                  <span className="text-xs leading-snug text-muted-foreground">
                    {pillar.tagline}
                  </span>
                </Link>
                {pillar.spec && (
                  <a
                    href={pillar.spec}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute right-2 top-2 rounded px-1 font-mono text-[9px] uppercase tracking-wider text-muted-foreground/70 transition-colors hover:text-primary"
                    aria-label={`${pillar.label} spec — opens in a new tab`}
                  >
                    spec ↗
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
