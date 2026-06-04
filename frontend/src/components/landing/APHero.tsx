"use client";

import Link from "next/link";
import { BRANDING } from "@/lib/branding";

/**
 * Landing hero — asymmetric editorial layout.
 *
 * Left column: eyebrow + two-line display headline + body + CTA pair.
 * Right column: a static "live pipeline" diagram showing the four-agent
 * sequence with a sample invoice trickling through it. The right column
 * is intentionally not interactive — it's a teaser. The interactive thing
 * is the CTA, which drops the visitor straight into the orchestrator chat.
 *
 * Typography: Montserrat (display) headline, JetBrains Mono (numbers)
 * for the invoice amount, Inter for body. Parse-blue is the conviction
 * color; AILANG-red is reserved for the family-attribution mark.
 */
export function APHero() {
  return (
    <section className="relative mx-auto w-full max-w-7xl px-6 pb-24 pt-16 md:px-10 md:pb-32 md:pt-24">
      <div className="grid items-start gap-12 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
        {/* LEFT — headline column */}
        <div className="flex flex-col gap-8">
          <Eyebrow text={BRANDING.demo.heroEyebrow} />

          <h1 className="font-display text-5xl font-bold leading-[0.95] tracking-tight text-foreground sm:text-6xl lg:text-7xl">
            {BRANDING.demo.heroLineA}
            <br />
            <span className="gradient-text-brand">{BRANDING.demo.heroLineB}</span>
          </h1>

          <p className="max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
            {BRANDING.demo.heroBody}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-3">
            <Link
              href={BRANDING.demo.chatHref}
              className="group inline-flex items-center gap-2 rounded-md bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground shadow-[0_0_18px_rgba(37,99,235,0.25)] transition-all hover:shadow-[0_0_28px_rgba(37,99,235,0.45)]"
            >
              {BRANDING.demo.ctaPrimary}
              <ArrowIcon className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href={BRANDING.demo.techHref}
              className="inline-flex items-center gap-2 rounded-md border border-border px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:border-primary/50 hover:text-primary"
            >
              {BRANDING.demo.ctaSecondary}
              <span aria-hidden className="text-muted-foreground">↗</span>
            </Link>
          </div>

          <SignalRow />
        </div>

        {/* RIGHT — pipeline diagram */}
        <PipelineDiagram />
      </div>
    </section>
  );
}

function Eyebrow({ text }: { text: string }) {
  return (
    <div className="inline-flex items-center gap-2 self-start rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
      </span>
      {text}
    </div>
  );
}

function SignalRow() {
  const items: { label: string; value: string }[] = [
    { label: "Agents", value: "4" },
    { label: "Protocols", value: "6" },
    { label: "LLM tokens / invoice parse", value: "0" },
  ];
  return (
    <dl className="mt-4 grid max-w-md grid-cols-3 gap-x-6 border-t border-border pt-6">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col gap-1">
          <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {it.label}
          </dt>
          <dd className="font-mono text-2xl font-semibold tabular-nums text-foreground">
            {it.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function PipelineDiagram() {
  // Static rendition of the live ap-orchestrator pipeline. Not connected to
  // any agent — it's a marketing teaser. The actual live version is
  // APPipelineSteps.tsx, but that needs a streaming session.
  const steps: { label: string; specialist: string; emit: string | null }[] = [
    { label: "Intake", specialist: "ap-orchestrator", emit: null },
    { label: "Extract", specialist: "invoice-extractor", emit: "emit_invoice_extraction" },
    { label: "Validate", specialist: "ap-validator", emit: "emit_ap_verdict" },
    { label: "Post", specialist: "ap-poster", emit: "emit_posting_record" },
  ];

  return (
    <div className="relative isolate">
      {/* Background plate with hairline border */}
      <div className="relative overflow-hidden rounded-xl border border-border bg-muted/30 p-6 backdrop-blur md:p-8">
        {/* Faint grid overlay */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              "linear-gradient(hsl(var(--primary)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--primary)) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />

        {/* Invoice "input" chip */}
        <div className="relative mb-6 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded border border-border bg-background">
            <DocumentIcon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="flex flex-1 flex-col gap-0.5">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Input
            </span>
            <span className="font-mono text-xs text-foreground">
              acme-gmbh-invoice-2026-042.docx
            </span>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            DOCX
          </span>
        </div>

        {/* Pipeline steps — vertical timeline */}
        <ol className="relative ml-4 space-y-4 border-l border-border pl-6">
          {steps.map((step, i) => (
            <li key={step.label} className="relative">
              {/* Dot */}
              <span
                aria-hidden
                className="absolute -left-[34px] flex h-6 w-6 items-center justify-center rounded-full border border-primary/40 bg-background"
              >
                <span className="font-mono text-[10px] font-bold text-primary">
                  {i + 1}
                </span>
              </span>
              <div className="flex items-baseline justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="font-display text-sm font-semibold text-foreground">
                    {step.label}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {step.specialist}
                  </span>
                </div>
                {step.emit && (
                  <span className="rounded-sm border border-primary/25 bg-primary/5 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-primary">
                    {step.emit}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ol>

        {/* "Output" card preview */}
        <div className="relative mt-6 rounded-md border border-primary/30 bg-primary/[0.04] p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-wider text-primary">
              A2UI Card · workspace surface
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">approved</span>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-xs">
            <span className="text-muted-foreground">vendor</span>
            <span className="text-right tabular-nums text-foreground">Acme GmbH</span>
            <span className="text-muted-foreground">total</span>
            <span className="text-right tabular-nums text-foreground">€4,250.00</span>
            <span className="text-muted-foreground">GL</span>
            <span className="text-right tabular-nums text-foreground">6020 · Materials</span>
            <span className="text-muted-foreground">verdict</span>
            <span className="text-right tabular-nums text-primary">post · auto-approve</span>
          </div>
        </div>
      </div>

      {/* Decorative annotation tag */}
      <div className="absolute -right-3 -top-3 hidden rotate-3 select-none rounded-sm border border-ailang/30 bg-background px-2 py-1 font-mono text-[9px] uppercase tracking-widest text-[hsl(var(--ailang))] md:block">
        powered by AILANG
      </div>
    </div>
  );
}

function ArrowIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DocumentIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M4 2h5l3 3v9H4V2z" strokeLinejoin="round" />
      <path d="M9 2v3h3M6 8h4M6 11h4" strokeLinecap="round" />
    </svg>
  );
}
