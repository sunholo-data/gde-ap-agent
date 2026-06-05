"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { getMetaByKey } from "@/lib/skillMeta";
import type { SpecialistKey } from "@/lib/auditViewFlag";
import type { SpecialistState, InvocationRecord } from "@/hooks/useSpecialistInvocations";
import { RunStandaloneSection } from "./RunStandaloneSection";
import { StandaloneResultView, type StandaloneResult } from "./StandaloneResultView";
import { VendorKgPanel } from "./VendorKgPanel";
import { InputOutputCard, SectionLabel } from "./sharedView";
import type { Skill } from "@/types/skill";
import type { DocTabData } from "@/components/doc-browser/DocTab";

interface InspectorPanelProps {
  open: boolean;
  specialistKey: SpecialistKey | null;
  state: SpecialistState | null;
  onClose: () => void;
  /** All skills available to the user — needed by RunStandaloneSection
   * to resolve specialist key → skillId. */
  skills: Skill[];
  /** Session ID for standalone runs + "Load last X" prefill. */
  sessionId: string | null;
  /** Current user uid — passed through to DocparsePicker for doc list. */
  uid: string;
  /** Click→chat handler for MCP App user-intent dispatch (KG citation /
   * vendor card clicks). Page-level routes to sendMessage. */
  onMcpUserIntent?: (intent: string, context?: Record<string, unknown>) => void;
  /** Per-specialist raw emissions captured from ADK session state.
   * Used to show the upstream specialist's output as the current
   * specialist's INPUT in the audit view — so each panel reveals the
   * data handoff (extractor → validator → poster) instead of showing
   * the emit_* args on both sides of the I/O card. */
  pipelineEmissions?: {
    invoice: Record<string, unknown> | null;
    verdict: Record<string, unknown> | null;
    posting: Record<string, unknown> | null;
  };
  /** Currently-open document tabs. Used to surface the extractor's
   * effective INPUT (parsed document(s) being processed) since the
   * extractor reads documents, not JSON. */
  openDocs?: DocTabData[];
}

/** Recovers from sessionStorage on mount — judges who refresh mid-demo
 * keep the audit panel they had open.
 */
export function loadPersistedInspectorKey(sessionId: string | null): SpecialistKey | null {
  if (!sessionId || typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(`ap-audit-open:${sessionId}`);
    if (raw === "docparse" || raw === "validator" || raw === "poster") return raw;
  } catch {
    // private mode / strict CSP
  }
  return null;
}

export function persistInspectorKey(sessionId: string | null, key: SpecialistKey | null): void {
  if (!sessionId || typeof window === "undefined") return;
  try {
    if (key) sessionStorage.setItem(`ap-audit-open:${sessionId}`, key);
    else sessionStorage.removeItem(`ap-audit-open:${sessionId}`);
  } catch {
    // ignore
  }
}

/**
 * Audit View side panel — slides in from the right when a SpecialistChip
 * is clicked. Renders the most recent invocation of that specialist
 * (input args, latency, structured result). M2 will replace the body
 * with a server-authored A2UI tree; M3 will add the Run-Standalone form.
 *
 * Persistent (not modal). 40% width on desktop, full overlay on mobile.
 */
export function InspectorPanel({
  open,
  specialistKey,
  state,
  onClose,
  skills,
  sessionId,
  uid,
  onMcpUserIntent,
  pipelineEmissions,
  openDocs,
}: InspectorPanelProps) {
  // ESC closes the panel
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // History dropdown selection — defaults to "current" (latest record).
  // Reset to current whenever specialistKey changes or new invocations land.
  const [selectedIdx, setSelectedIdx] = useState<number | "current">("current");
  useEffect(() => {
    setSelectedIdx("current");
  }, [specialistKey, state?.current?.id]);

  // Lifted "Run Standalone" result — rendered as the main body when set
  // so the agent's tool calls + their structured outputs are the first
  // thing the user sees, not buried in a footer disclosure. Clears on
  // chip change to avoid showing yesterday's docparse result while
  // viewing the validator.
  const [standaloneResult, setStandaloneResult] = useState<StandaloneResult | null>(null);
  const [standaloneRunning, setStandaloneRunning] = useState(false);
  useEffect(() => {
    setStandaloneResult(null);
    setStandaloneRunning(false);
  }, [specialistKey]);

  if (!open || !specialistKey) return null;
  const meta = getMetaByKey(specialistKey);
  const history = state?.history ?? [];
  const current = state?.current ?? null;
  const displayRecord =
    selectedIdx === "current" ? current : (history[selectedIdx] ?? current);

  return (
    <aside
      data-testid="inspector-panel"
      role="complementary"
      aria-label={`Audit view: ${meta.tagline}`}
      className={cn(
        "fixed inset-y-0 right-0 z-30 flex w-full flex-col border-l border-border bg-background shadow-2xl",
        // Slide in from the right when opened. `animate-in` runs once
        // at mount (the panel is only mounted while open, so each open
        // → close → reopen cycle gets the entrance animation fresh).
        "animate-in slide-in-from-right-8 fade-in duration-250 ease-out",
        "md:w-[40%] md:max-w-[600px]",
      )}
    >
      {/* Header */}
      <header className="flex shrink-0 items-center gap-2 border-b border-border bg-background/95 px-4 py-3">
        <span className="shrink-0 text-primary">{meta.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-sm font-semibold text-foreground">{meta.tagline}</h2>
            <span className="rounded-full border border-primary/20 bg-primary/8 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary/80">
              Audit View
            </span>
          </div>
          <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{meta.description}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close audit view"
          className="shrink-0 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/30 hover:text-foreground"
        >
          ✕
        </button>
      </header>

      {/* History selector (shown when >1 invocation in session) */}
      {history.length > 1 && (
        <div className="flex shrink-0 items-center gap-2 border-b border-border bg-muted/20 px-4 py-2">
          <label
            htmlFor="audit-history"
            className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/60"
          >
            Invocation
          </label>
          <select
            id="audit-history"
            value={selectedIdx === "current" ? "current" : String(selectedIdx)}
            onChange={(e) =>
              setSelectedIdx(e.target.value === "current" ? "current" : Number(e.target.value))
            }
            className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
          >
            <option value="current">Latest</option>
            {history
              .map((rec, idx) => ({ rec, idx }))
              .reverse()
              .map(({ rec, idx }) => (
                <option key={rec.id} value={idx}>
                  #{idx + 1} · {formatRelativeTime(rec.startedAt)} · {rec.status}
                </option>
              ))}
          </select>
          <span className="text-[10px] text-muted-foreground/50">
            {history.length} this session
          </span>
        </div>
      )}

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* "Running…" indicator while the standalone POST is in flight */}
        {standaloneRunning && (
          <div
            data-testid="audit-standalone-running"
            className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-[11px] text-primary"
          >
            <span
              aria-hidden
              className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent"
            />
            Running standalone invocation…
          </div>
        )}

        {/* Standalone-run result is the primary body when present —
            agent tool calls + outputs appear at the top, not in a
            collapsed footer. */}
        {standaloneResult && (
          <StandaloneResultView
            result={standaloneResult}
            onClear={() => setStandaloneResult(null)}
          />
        )}

        {/* Orchestrator-driven invocation (chip lit up from the pipeline)
            renders here. Pushed below the standalone result when both
            exist — the user's most recent action is most visible. */}
        {displayRecord ? (
          <InvocationBody
            record={displayRecord}
            upstreamInput={resolveUpstreamInput(
              specialistKey,
              pipelineEmissions,
              openDocs,
            )}
            upstreamLabel={resolveUpstreamLabel(specialistKey)}
          />
        ) : !standaloneResult && !standaloneRunning ? (
          <EmptyState specialistKey={specialistKey} />
        ) : null}

        {/* Protocol-trio showcase: validator panel embeds the
            ap-vendor-kg MCP App so AG-UI + A2UI + MCP Apps appear
            together in one place. See multi-agent-inspector-ux.md. */}
        {specialistKey === "validator" && (
          <div>
            <h3 className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/60">
              Vendor knowledge graph (MCP App)
            </h3>
            <VendorKgPanel
              resultJson={displayRecord?.resultContent}
              onUserIntent={onMcpUserIntent}
            />
          </div>
        )}
      </div>

      {/* Footer — Run Standalone form. Results lift up to the body
          above so the structured output is the first thing the user
          sees, not buried behind a disclosure. */}
      <footer className="shrink-0 border-t border-border bg-muted/30 px-4 py-2.5">
        <RunStandaloneSection
          specialistKey={specialistKey}
          sessionId={sessionId}
          skills={skills}
          uid={uid}
          onResult={setStandaloneResult}
          onSubmittingChange={setStandaloneRunning}
        />
      </footer>
    </aside>
  );
}

function EmptyState({ specialistKey }: { specialistKey: SpecialistKey }) {
  const meta = getMetaByKey(specialistKey);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-12 text-center">
      <span className="text-primary/40">{meta.icon}</span>
      <p className="text-sm font-semibold text-muted-foreground">No invocations yet</p>
      <p className="max-w-xs text-xs text-muted-foreground/70">
        This specialist hasn&apos;t been called in the current session. Send an invoice through the
        orchestrator chat and watch this panel light up.
      </p>
    </div>
  );
}

function InvocationBody({
  record,
  upstreamInput,
  upstreamLabel,
}: {
  record: InvocationRecord;
  upstreamInput?: string | null;
  upstreamLabel?: string;
}) {
  const latencyMs =
    record.endedAt !== null ? record.endedAt - record.startedAt : null;

  // For function-as-schema emit_* tools the args ARE the specialist's
  // OUTPUT. The INPUT side should show the upstream specialist's
  // output (the data handoff) rather than mirroring the same args
  // back — which is what the previous version did, making all three
  // audit views look identical.
  const isEmit = record.name.startsWith("emit_");
  const inputJson = isEmit && upstreamInput ? upstreamInput : record.argsJson;
  const inputLabel = isEmit && upstreamInput && upstreamLabel
    ? upstreamLabel
    : "Input (orchestrator → specialist)";

  return (
    <section
      data-testid="audit-orchestrator-invocation"
      className="space-y-3 rounded-lg border border-border bg-muted/20 p-3"
    >
      <header className="flex items-center gap-2">
        <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary">
          Orchestrator-driven
        </span>
        <StatusPill status={record.status} />
        {latencyMs !== null && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {latencyMs < 1000 ? `${Math.round(latencyMs)}ms` : `${(latencyMs / 1000).toFixed(2)}s`}
          </span>
        )}
        <span className="truncate font-mono text-[10px] text-muted-foreground/60">{record.name}</span>
      </header>

      <div>
        <SectionLabel>Structured I/O</SectionLabel>
        <div className="mt-1">
          {/* For function-as-schema emit_* tools, the args ARE the canonical
              emitted payload — the tool result is just a STOP signal to the
              orchestrator. Show args on the Output side, and the upstream
              specialist's emission on the Input side so the data handoff
              between Extract → Validate → Post is visible. */}
          <InputOutputCard
            title={record.name}
            input={inputJson}
            output={
              record.name.startsWith("emit_") && record.argsJson
                ? record.argsJson
                : record.resultContent
            }
            inputLabel={inputLabel}
            outputLabel={
              record.name.startsWith("emit_")
                ? "Emitted payload (function-as-schema)"
                : "Output (specialist → orchestrator)"
            }
            emptyOutputMessage={record.status === "active" ? "(awaiting result…)" : "(no result captured)"}
          />
        </div>
      </div>
    </section>
  );
}

function formatRelativeTime(ts: number): string {
  const delta = Date.now() - ts;
  if (delta < 1000) return "just now";
  if (delta < 60_000) return `${Math.round(delta / 1000)}s ago`;
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
  return new Date(ts).toLocaleTimeString();
}

/**
 * Resolve what to show as the SPECIALIST'S UPSTREAM INPUT in the audit
 * view (i.e., what the previous stage handed them). Different per key:
 *
 *   docparse  → effectively reads a document, not JSON. Show the open
 *               doc tabs as a tiny synthetic JSON for context.
 *   validator → the extractor's emitted invoice.
 *   poster    → the extractor's invoice + validator's verdict.
 *
 * Returns null when the upstream emission isn't available yet — the
 * caller falls back to record.argsJson and the panel reads identically
 * to the pre-fix behaviour.
 */
function resolveUpstreamInput(
  specialistKey: SpecialistKey | null,
  pipelineEmissions: InspectorPanelProps["pipelineEmissions"],
  openDocs: InspectorPanelProps["openDocs"],
): string | null {
  if (!specialistKey) return null;
  if (specialistKey === "docparse") {
    const docs = openDocs?.filter((t) => t.included) ?? [];
    if (docs.length === 0) return null;
    const summary = docs.map((d) => ({
      doc_id: d.id,
      filename: d.filename,
      format: d.format,
      parse_status: d.parseStatus ?? "loaded",
      block_count: d.blockCount ?? null,
    }));
    return JSON.stringify(
      {
        task: "Extract structured invoice fields from the attached document(s).",
        documents: summary,
      },
      null,
      2,
    );
  }
  if (specialistKey === "validator") {
    const invoice = pipelineEmissions?.invoice;
    return invoice ? JSON.stringify(invoice, null, 2) : null;
  }
  if (specialistKey === "poster") {
    const invoice = pipelineEmissions?.invoice;
    const verdict = pipelineEmissions?.verdict;
    if (!invoice && !verdict) return null;
    return JSON.stringify(
      { invoice: invoice ?? null, verdict: verdict ?? null },
      null,
      2,
    );
  }
  return null;
}

function resolveUpstreamLabel(specialistKey: SpecialistKey | null): string {
  if (specialistKey === "docparse") return "Input — parsed document(s) attached";
  if (specialistKey === "validator") return "Input — invoice handed off by Extractor";
  if (specialistKey === "poster") return "Input — invoice + verdict handed off by Validator";
  return "Input (orchestrator → specialist)";
}

function StatusPill({ status }: { status: "idle" | "active" | "done" | "error" }) {
  const config = {
    idle: { label: "Idle", cls: "border-border bg-background text-muted-foreground" },
    active: { label: "Running…", cls: "border-primary/40 bg-primary/10 text-primary" },
    done: { label: "Done", cls: "border-primary/40 bg-primary/10 text-primary" },
    error: { label: "Error", cls: "border-destructive/40 bg-destructive/10 text-destructive" },
  }[status];
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider", config.cls)}>
      {config.label}
    </span>
  );
}
