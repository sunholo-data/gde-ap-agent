import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import { BrandFooter } from "@/components/BrandFooter";
import { ProtocolDiagram } from "@/components/tech/ProtocolDiagram";
import { ArchitectureDiagram } from "@/components/tech/ArchitectureDiagram";
import { ProtocolIcon } from "@/components/tech/ProtocolIcon";
import { BRANDING } from "@/lib/branding";

export const metadata: Metadata = {
  title: `Tech stack · ${BRANDING.appName}`,
  description:
    "How the AP showcase is built — AILANG Parse, Google ADK, A2UI, MCP Apps, AG-UI, A2A. One protocol per problem; everything inspectable.",
};

/**
 * /tech — judges-facing technical breakdown.
 *
 * The pitch is: every claim in the live demo is backed by a specific
 * protocol or piece of infrastructure. This page enumerates them, says
 * what each one does *in this demo* (not in the abstract), and points at
 * the file where the integration lives. Content is intentionally
 * editorial — dense type, hairline rules, monospace for protocol names
 * and identifiers. Lift-source: SUBMISSION.md.
 */

type PillarKey = "ailang" | "adk" | "a2ui" | "mcp-apps" | "ag-ui" | "a2a";

interface PillarSection {
  key: PillarKey;
  label: string;
  role: string;
  doesInDemo: string;
  whereToSee: string;
  source: { label: string; href: string };
  isFamily?: boolean;
}

const PILLARS: PillarSection[] = [
  {
    key: "ailang",
    label: "AILANG",
    role: "Deterministic parse + effect-typed code generation",
    doesInDemo:
      "Reads invoices (DOCX, ODT, XLSX, EML, PDF) into structured JSON without burning a single LLM token on extraction. AILANG's effect system guarantees the parser can't perform any side-effect outside the parse — what comes out is auditable by construction.",
    whereToSee:
      "Run the demo and watch the Extract step in the pipeline rail finish in under a second on a clean DOCX. That's pure AILANG — Gemini is never asked to read the file.",
    source: { label: "ailang.sunholo.com", href: BRANDING.links.ailang },
    isFamily: true,
  },
  {
    key: "adk",
    label: "Google ADK",
    role: "Multi-agent orchestration framework",
    doesInDemo:
      "Four declarative SKILL.md files plus a SequentialAgent compose the AP pipeline (Intake → Extract → Validate → Post). No hand-rolled routing code: the workflow is deterministic Python orchestration, sub-agent dispatch is resolved by the ADK runtime, and session/memory/artifact services are stock ADK.",
    whereToSee:
      "backend/skills/templates/ap-orchestrator/SKILL.md plus the three specialist SKILL.md siblings. Open the Audit View on any specialist chip to see the ADK Runner trace.",
    source: { label: "google.github.io/adk-docs", href: "https://google.github.io/adk-docs/" },
  },
  {
    key: "a2ui",
    label: "A2UI",
    role: "Declarative agent UI (Agents-to-UI)",
    doesInDemo:
      "Every emit_* tool the pipeline calls writes a typed JSON payload that the frontend renders as an A2UI Card — invoice extraction, AP verdict, posting record. No bespoke component per skill: the same renderer handles every emit_* payload across the whole product, courtesy of the JsonAsA2UICard adapter.",
    whereToSee:
      "Right-hand 'workspace' surface during a pipeline run. Each completed step pushes a Card with full inspectable detail.",
    source: { label: "agent-to-ui spec", href: "https://github.com/agentic-protocols/a2ui" },
  },
  {
    key: "mcp-apps",
    label: "MCP Apps",
    role: "Sandboxed iframe artifacts with postMessage handshake",
    doesInDemo:
      "Two MCP Apps ride alongside the pipeline: the Vendor Globe (an animated globe.gl visualisation arcing from your invoice's origin) and the AP Analytics Dashboard (aging, vendor mix, GL breakdown — Chart.js, canvas-only, no CDN bloat). Both run on a separate-origin Cloud Run service, talk to the host via the spec's postMessage handshake.",
    whereToSee:
      "Ask the agent 'show me the vendor on a map' or 'open the AP dashboard' mid-conversation. The artefacts mount into the workspace pane.",
    source: { label: "modelcontextprotocol.io/apps", href: "https://modelcontextprotocol.io" },
  },
  {
    key: "ag-ui",
    label: "AG-UI",
    role: "Streaming event protocol between agent and client",
    doesInDemo:
      "The four-step pipeline rail you watch animate during a run is driven by AG-UI TOOL_CALL_START/END and STAGE_PROGRESS events streamed over SSE. The same channel carries the thinking output, the emit_* tool payloads, and the final assistant message — one connection, every observable.",
    whereToSee:
      "Open the browser DevTools Network panel during a run — the /chat/stream request stays open and you can watch the event stream tick.",
    source: { label: "ag-ui.com", href: "https://ag-ui.com" },
  },
  {
    key: "a2a",
    label: "A2A",
    role: "Agent-to-Agent discovery + capability negotiation",
    doesInDemo:
      "The ap-orchestrator publishes an /.well-known/agent.json with its full capability profile and X-A2A-Extensions header support. That makes it registerable with Gemini Enterprise as a managed agent without code changes — discovery and handshake follow the A2A spec.",
    whereToSee:
      "curl https://gde-ap-agent-blqtqfexwa-ew.a.run.app/.well-known/agent.json — every field is there.",
    source: { label: "a2aproject.dev", href: "https://a2aproject.dev" },
  },
];

const DEMO_FLOW: { step: string; what: string }[] = [
  { step: "01", what: "Land on the orchestrator chat, pick a sample invoice or drop your own." },
  { step: "02", what: "Pipeline rail animates Intake → Extract → Validate → Post in real time." },
  { step: "03", what: "Each completed step pushes an inspectable A2UI Card to the workspace pane." },
  { step: "04", what: "Click any specialist chip on the audit view to inspect tools, input, output." },
  { step: "05", what: "Ask 'show the vendor on a map' — the Vendor Globe MCP App mounts inline." },
  { step: "06", what: "Ask 'open the AP dashboard' — analytics MCP App embeds with the live invoice." },
  { step: "07", what: "Every decision is traceable to a specific tool call you can re-run standalone." },
];

export default function TechPage() {
  return (
    <main className="relative min-h-screen pb-16">
      <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4 md:px-10">
          <Link href="/" className="flex items-center gap-2.5" aria-label="Back to landing">
            <Image
              src={BRANDING.logo.heroAnimated}
              alt=""
              width={28}
              height={28}
              className="h-7 w-7"
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              ailang-parse · AP Showcase
            </span>
          </Link>
          <Link
            href={BRANDING.demo.chatHref}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-[0_0_12px_rgba(37,99,235,0.25)] transition-all hover:shadow-[0_0_20px_rgba(37,99,235,0.4)]"
          >
            {BRANDING.demo.ctaPrimary} →
          </Link>
        </div>
      </header>

      <article className="mx-auto w-full max-w-5xl px-6 py-16 md:px-10 md:py-24">
        {/* Hero / framing */}
        <section className="mb-20">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-muted/40 px-3 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            For the judges
          </div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-foreground md:text-6xl">
            One protocol per problem.
            <br />
            <span className="gradient-text-brand">Everything inspectable.</span>
          </h1>
          <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground">
            The AP showcase isn't a monolithic app with an &ldquo;AI feature.&rdquo; It&apos;s a
            stack of six narrow protocols, each doing one thing well, composed into a
            multi-agent pipeline where every step you see on the screen maps to a specific
            file, function, or wire event.
          </p>
        </section>

        {/* Architecture diagram (animated) */}
        <section className="mb-20">
          <SectionLabel>The architecture</SectionLabel>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            One invoice, end-to-end.
          </h2>
          <p className="mt-3 max-w-2xl text-base text-muted-foreground">
            What actually happens between &ldquo;Try the demo&rdquo; and a posting record in
            the audit pane. Each edge is a real protocol carrying real traffic — animated
            so you can see the direction of flow.
          </p>
          <div className="mt-8">
            <ArchitectureDiagram />
          </div>
        </section>

        {/* Protocol diagram — layered view */}
        <section className="mb-20">
          <SectionLabel>The layered view</SectionLabel>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            Four layers, six protocols, one demo.
          </h2>
          <p className="mt-3 max-w-2xl text-base text-muted-foreground">
            The same stack, flattened. Each layer is replaceable in isolation — that&apos;s
            why we&apos;re betting on protocols rather than a vertically-integrated framework.
          </p>
          <div className="mt-8">
            <ProtocolDiagram />
          </div>
        </section>

        {/* Per-pillar deep dive */}
        <section className="mb-20 space-y-16">
          <div>
            <SectionLabel>What each piece does</SectionLabel>
            <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
              Six pillars, in order.
            </h2>
            <p className="mt-3 max-w-2xl text-base text-muted-foreground">
              AILANG leads — it&apos;s ours, and it&apos;s the reason the demo can promise
              zero-LLM-token extraction. Everything else is industry protocol, picked for fit.
            </p>
          </div>

          {PILLARS.map((pillar, i) => (
            <PillarBlock key={pillar.key} pillar={pillar} index={i + 1} />
          ))}
        </section>

        {/* Demo flow walkthrough */}
        <section className="mb-20">
          <SectionLabel>The walkthrough</SectionLabel>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            What you will see in 90 seconds.
          </h2>
          <ol className="mt-8 divide-y divide-border overflow-hidden rounded-lg border border-border">
            {DEMO_FLOW.map((row) => (
              <li
                key={row.step}
                className="grid grid-cols-[auto_1fr] gap-x-6 bg-background p-5 md:p-6"
              >
                <span className="font-mono text-sm font-bold tabular-nums text-primary">
                  {row.step}
                </span>
                <p className="text-sm leading-relaxed text-foreground md:text-base">{row.what}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Where to find it / deploy story */}
        <section className="mb-20">
          <SectionLabel>Deployed surface</SectionLabel>
          <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
            Where to verify each claim.
          </h2>
          <div className="mt-8 grid gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-2">
            <DeployRow
              label="Frontend + backend"
              value="gde-ap-agent-blqtqfexwa-ew.a.run.app"
              note="Single Cloud Run service. Next.js front, FastAPI on /api/* via reverse proxy."
            />
            <DeployRow
              label="MCP App sandbox"
              value="mcp-sandbox-374404277595.europe-west1.run.app"
              note="Separate-origin Cloud Run. Vendor Globe + AP Analytics + Vendor KG artefacts."
            />
            <DeployRow
              label="Agent card (A2A)"
              value="/.well-known/agent.json"
              note="Discovery surface for Gemini Enterprise registration."
            />
            <DeployRow
              label="OpenAPI"
              value="/openapi.json"
              note="Full API surface — sessions, skills, documents, A2UI surface actions."
            />
          </div>
        </section>

        {/* Closing CTA */}
        <section className="mt-24 flex flex-col items-center gap-4 border-t border-border pt-16 text-center">
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            That&apos;s the stack
          </p>
          <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
            See it run.
          </h2>
          <Link
            href={BRANDING.demo.chatHref}
            className="group mt-2 inline-flex items-center gap-2 rounded-md bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-[0_0_18px_rgba(37,99,235,0.25)] transition-all hover:shadow-[0_0_28px_rgba(37,99,235,0.45)]"
          >
            {BRANDING.demo.ctaPrimary}
            <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
          </Link>
        </section>
      </article>

      <BrandFooter />
    </main>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
      {children}
    </span>
  );
}

function PillarBlock({ pillar, index }: { pillar: PillarSection; index: number }) {
  return (
    <div id={pillar.key} className="scroll-mt-24">
      <div className="grid gap-8 lg:grid-cols-[auto_1fr] lg:gap-12">
        {/* Index + label */}
        <div className="flex shrink-0 items-start gap-4 lg:w-64 lg:flex-col lg:items-start lg:gap-3">
          <span className="font-mono text-xs font-bold tabular-nums text-primary">
            {String(index).padStart(2, "0")}
          </span>
          <ProtocolIcon
            pillar={pillar.key}
            className={[
              "h-10 w-10",
              pillar.isFamily ? "text-ailang" : "text-foreground/80",
            ].join(" ")}
          />
          <h3
            className={[
              "font-display text-3xl font-bold tracking-tight md:text-4xl",
              pillar.isFamily ? "text-ailang" : "text-foreground",
            ].join(" ")}
          >
            {pillar.label}
          </h3>
          <p className="hidden text-xs uppercase tracking-wider text-muted-foreground lg:block">
            {pillar.role}
          </p>
        </div>

        {/* Body */}
        <div className="space-y-6">
          <p className="text-base leading-relaxed text-foreground md:text-lg">
            {pillar.doesInDemo}
          </p>

          <div className="rounded-md border border-border bg-muted/30 p-4">
            <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Where to see it
            </p>
            <p className="text-sm leading-relaxed text-foreground">{pillar.whereToSee}</p>
          </div>

          <a
            href={pillar.source.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-primary transition-colors hover:text-primary/80"
          >
            <span aria-hidden>↗</span>
            {pillar.source.label}
          </a>
        </div>
      </div>

      <div className="mt-12 h-px w-full bg-border" />
    </div>
  );
}

function DeployRow({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-1.5 bg-background p-5">
      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <code className="break-all font-mono text-sm text-foreground">{value}</code>
      <span className="text-xs leading-snug text-muted-foreground">{note}</span>
    </div>
  );
}
