import { BRANDING } from "@/lib/branding";

interface BrandFooterProps {
  /** "full" (welcome screen) or "slim" (chat shell). Defaults to "full". */
  variant?: "full" | "slim";
}

export function BrandFooter({ variant = "full" }: BrandFooterProps) {
  if (variant === "slim") {
    return (
      <footer className="flex w-full shrink-0 items-center justify-center gap-1.5 border-t border-border/40 bg-background px-4 py-1.5 text-[10px] text-muted-foreground/70">
        <span>Part of</span>
        <a
          className="inline-flex items-center gap-1 hover:text-[hsl(var(--ailang))]"
          href={BRANDING.links.ailang}
          target="_blank"
          rel="noopener noreferrer"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={BRANDING.logo.familyMark} alt="" className="h-3 w-3" />
          <span>AILANG</span>
        </a>
        <span>·</span>
        <span>powered by</span>
        <a
          className="inline-flex items-center gap-1 hover:text-primary"
          href={BRANDING.links.ailangParse}
          target="_blank"
          rel="noopener noreferrer"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={BRANDING.logo.chatAvatar} alt="" className="h-3 w-3" />
          <span>ailang-parse</span>
        </a>
      </footer>
    );
  }

  return (
    <footer className="w-full border-t border-border/50 bg-background/50 px-4 py-3 text-center text-[11px] text-muted-foreground">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-x-3 gap-y-1">
        <span className="font-display font-semibold">{BRANDING.appName}</span>
        <span aria-hidden="true">·</span>
        <a
          className="inline-flex items-center gap-1 hover:text-primary"
          href={BRANDING.links.ailangParse}
          target="_blank"
          rel="noopener noreferrer"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={BRANDING.logo.chatAvatar} alt="" className="h-3.5 w-3.5" />
          <span>ailang-parse ↗</span>
        </a>
        <a
          className="inline-flex items-center gap-1 hover:text-[hsl(var(--ailang))]"
          href={BRANDING.links.ailang}
          target="_blank"
          rel="noopener noreferrer"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={BRANDING.logo.familyMark} alt="" className="h-3.5 w-3.5" />
          <span>AILANG ↗</span>
        </a>
        <a
          className="hover:text-foreground"
          href={BRANDING.links.sunholo}
          target="_blank"
          rel="noopener noreferrer"
        >
          Sunholo ↗
        </a>
      </div>
    </footer>
  );
}
