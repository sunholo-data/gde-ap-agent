import { BRANDING } from "@/lib/branding";
import type { DocSummary } from "@/hooks/useDocument";

interface DocumentFooterProps {
  summary: DocSummary | null;
  /** Wall-clock parse duration in ms. When set, the footer renders
   * AILANG Parse attribution with the elapsed time. */
  parsedMs?: number | null;
}

function formatParseTime(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

export function DocumentFooter({ summary, parsedMs }: DocumentFooterProps) {
  const stats = summary
    ? [
        { label: "blocks", value: summary.totalBlocks },
        { label: "tables", value: summary.tables },
        { label: "images", value: summary.images },
        { label: "changes", value: summary.changes },
      ].filter((s) => s.value > 0)
    : [];

  const hasAttribution = parsedMs !== null && parsedMs !== undefined;
  if (stats.length === 0 && !hasAttribution) return null;

  return (
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-border/60 px-3 py-1.5 text-[10px] text-muted-foreground">
      <div>
        {stats.map((s, i) => (
          <span key={s.label}>
            {i > 0 && " · "}
            {s.value} {s.label}
          </span>
        ))}
      </div>
      {hasAttribution && (
        // Subtle but noticeable AILANG Parse attribution. Two small
        // logos flank the family / product name, both clickable; the
        // parse time sits on the right as a mono pill so the
        // deterministic-parse story (≤1s typical) lands without a
        // separate "look at this!" callout.
        <a
          href={BRANDING.links.ailangParse}
          target="_blank"
          rel="noopener noreferrer"
          className="group inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-background/60 px-2 py-0.5 font-mono uppercase tracking-wider text-muted-foreground/80 transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
          title="Parsed locally by AILANG Parse — deterministic, no LLM tokens"
        >
          <span className="text-[9px] tracking-[0.14em]">Parsed by</span>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={BRANDING.logo.familyMark}
            alt=""
            className="h-3 w-3 opacity-70 transition-opacity group-hover:opacity-100"
            aria-hidden="true"
          />
          <span className="text-[10px] font-semibold tracking-wider">AILANG Parse</span>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={BRANDING.logo.chatAvatar}
            alt=""
            className="h-3 w-3 opacity-70 transition-opacity group-hover:opacity-100"
            aria-hidden="true"
          />
          <span aria-hidden="true" className="mx-0.5 text-muted-foreground/40">·</span>
          <span className="font-mono tabular-nums text-[10px] text-foreground/80">
            {formatParseTime(parsedMs!)}
          </span>
        </a>
      )}
    </div>
  );
}
