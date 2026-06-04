import Link from "next/link";
import { BRANDING } from "@/lib/branding";

/**
 * Bottom-of-landing "how does the demo actually work" block. Three steps
 * pointed at the things a judge will do in the next 90 seconds. Closes
 * with a second CTA so they don't have to scroll back to the hero.
 */
const STEPS: { num: string; title: string; body: string }[] = [
  {
    num: "01",
    title: "Pick a sample invoice",
    body: "Three fixtures pre-loaded — DOCX, ODT, EML — so you can demo the pipeline without finding your own file. Or drop your own invoice in.",
  },
  {
    num: "02",
    title: "Watch the four-agent pipeline run",
    body: "Intake → Extract → Validate → Post. Each step emits a structured A2UI Card the moment it completes — no JSON-staring required.",
  },
  {
    num: "03",
    title: "Open the audit view",
    body: "Click any specialist chip to see exactly which tools fired, what input each agent saw, and what it returned. Every decision is inspectable.",
  },
];

export function DemoSteps() {
  return (
    <section className="mx-auto w-full max-w-7xl px-6 py-20 md:px-10 md:py-28">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          The 90-second tour
        </h2>
        <p className="mt-3 font-display text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
          A demo that explains itself.
        </p>
        <p className="mt-3 text-base text-muted-foreground">
          No video, no slide deck. Every claim the agent makes shows up in a Card you can click into.
        </p>
      </div>
      <ol className="mt-14 grid gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-3">
        {STEPS.map((step) => (
          <li key={step.num} className="flex flex-col gap-3 bg-background p-6 md:p-8">
            <span className="font-mono text-xs font-bold tabular-nums text-primary">
              {step.num}
            </span>
            <h3 className="font-display text-lg font-semibold tracking-tight text-foreground">
              {step.title}
            </h3>
            <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
          </li>
        ))}
      </ol>
      <div className="mt-14 flex flex-col items-center gap-3">
        <Link
          href={BRANDING.demo.chatHref}
          className="group inline-flex items-center gap-2 rounded-md bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-[0_0_18px_rgba(37,99,235,0.25)] transition-all hover:shadow-[0_0_28px_rgba(37,99,235,0.45)]"
        >
          {BRANDING.demo.ctaPrimary}
          <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
        </Link>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          No signup required for the demo
        </span>
      </div>
    </section>
  );
}
