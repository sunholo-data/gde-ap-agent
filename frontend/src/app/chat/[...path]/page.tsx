"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BrandFooter } from "@/components/BrandFooter";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import type { DocTabData } from "@/components/doc-browser/DocTab";
import { DocListView } from "@/components/doc-browser/DocListView";
import { GCSFileBrowser } from "@/components/doc-browser/GCSFileBrowser";
import { DocTabsBar } from "@/components/doc-browser/DocTabsBar";
import { UploadDropZone } from "@/components/doc-browser/UploadDropZone";
import type { ParsedDocument } from "@/hooks/useDocBrowser";
import { useAuth } from "@/contexts/AuthContext";
import type { User } from "@/lib/firebase";
import { useSkillAgent, type StreamError } from "@/hooks/useSkillAgent";
import { useSkillMeta } from "@/hooks/useSkillMeta";
import { useUserSkills } from "@/hooks/useUserSkills";
import { useSessionMessages } from "@/hooks/useSessionMessages";
import { useSessionDocuments } from "@/hooks/useSessionDocuments";
import { useStableThreadId } from "@/hooks/useStableThreadId";
import { fetchWithAuth } from "@/lib/apiClient";
import { computeIncludedDocIds } from "@/lib/docContext";
import { notifySessionsChanged, subscribeSessionsChangedDetailed } from "@/lib/sessionEvents";
import { useSkillSessions } from "@/hooks/useSkillSessions";
import { useSlugResolution } from "@/hooks/useSlugResolution";
import { SkillSessionPanel } from "@/components/chat/SkillSessionPanel";
import DocumentHistoryPanel from "@/components/chat/DocumentHistoryPanel";
import { SkillsBar } from "@/components/navigation/SkillsBar";
import { getSkillMeta, findSkillByMetaKey } from "@/lib/skillMeta";
import {
  InspectorPanel,
  loadPersistedInspectorKey,
  persistInspectorKey,
} from "@/components/audit/InspectorPanel";
import { useSpecialistInvocations } from "@/hooks/useSpecialistInvocations";
import { isAuditViewEnabled, type SpecialistKey } from "@/lib/auditViewFlag";
import { skillHref } from "@/components/navigation/skillHref";
import { SampleInvoicePicker } from "@/components/chat/SampleInvoicePicker";
import { Workbench, useTabBadges, type WorkbenchTab } from "@/components/chat/Workbench";
import { AGUIProvider } from "@/providers/AGUIProvider";
import {
  SurfaceRegistryProvider,
  useClearSurfacesOnSessionChange,
  useSurfaceState,
} from "@/providers/SurfaceRegistry";
import { A2UISurfaceMount } from "@/components/protocols/A2UISurfaceMount";
import { InvoiceHeroCard } from "@/components/chat/InvoiceHeroCard";
import { VendorKgPanel } from "@/components/audit/VendorKgPanel";
import { DocumentPanel } from "@/components/document/DocumentPanel";
import { LatencyHUD } from "@/components/dev/LatencyHUD";
import { APDashboardPanel, type InvoiceData as DashboardInvoice } from "@/components/workspace/APDashboardPanel";

/**
 * MULTI-SURFACE-A2UI M3 — chat page surface mounts.
 *
 * The chat page wraps in <SurfaceRegistryProvider> and declares mounts for
 * the four named A2UI surfaces. Each mount is conditional on having content
 * — empty surfaces don't add visible DOM. Layout intent:
 *   - workspace : displaces or sits alongside the DocumentPanel (w-1/2 region)
 *   - sidebar   : appends to the bottom of the existing aside
 *   - modal     : fixed-position overlay at page root (M4 wires the
 *                 user-gesture guard; M3 just shows it when populated)
 */
function WorkspaceSurfaceRegion({
  sessionId,
  onAction,
}: {
  sessionId: string | null;
  onAction?: (event: { actionName: string; context: Record<string, unknown> }) => void;
}) {
  const state = useSurfaceState("workspace");
  if (!state?.surface) return null;
  // Workspace is a flex sibling of the chat panel. Each gets `flex-1
  // min-w-0` so they share the parent row proportionally and BOTH can
  // shrink below their natural content size when the viewport is narrow.
  // `max-w-xl` caps the workspace so it doesn't dominate on wide screens;
  // the chat is the primary interaction surface and shouldn't be squeezed
  // by small dashboard content. Cap is generous (576px) — forks with
  // larger dashboards override via SurfaceRegistry policy.
  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r md:max-w-xl">
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <A2UISurfaceMount
          surfaceId="workspace"
          className="h-full"
          sessionId={sessionId}
          onAction={onAction}
        />
      </div>
    </div>
  );
}

/**
 * AP-orchestrator workbench: replaces the prior single-slot conditional
 * ladder with a persistent tabbed pane (Invoice · Document · Vendor ·
 * Analytics). All tabs stay mounted so MCP App iframes (Globe, KG,
 * Dashboard) don't remount on every switch — the postMessage handshake
 * is expensive and remounting would force a re-init flash.
 *
 * Tab badges fire when content updates while the tab is inactive
 * (e.g. workspace surface receives a new emit_* payload while user is
 * on Vendor tab) and clear the moment the user switches to it.
 *
 * The Dashboard's `surface_action` event from the agent still lands
 * via handleAction in the parent — it updates dashboardOpen, which
 * this component watches to badge the Analytics tab.
 */
/**
 * Project the merged emit_* payload into the dashboard's InvoiceData
 * shape so the AP Analytics tab updates automatically after every
 * pipeline run — without requiring the orchestrator to fire the
 * `show_ap_dashboard` action. Returns null when no extraction has
 * happened. Keeps the same field mapping as the `show_ap_dashboard`
 * action handler, refactored out for reuse.
 */
function dashboardInvoiceFromEmitted(
  payload: Record<string, unknown> | null,
): DashboardInvoice | null {
  if (!payload) return null;
  const vendorName = typeof payload.vendor_name === "string" ? payload.vendor_name : "";
  if (!vendorName) return null;
  const v = typeof payload.verdict === "string" ? payload.verdict : "";
  const status: DashboardInvoice["status"] =
    /pass|approve|post/i.test(v)
      ? "approved"
      : /review/i.test(v)
        ? "needs_review"
        : /fail|reject|block|exception/i.test(v)
          ? "exception"
          : "pending";
  const totalRaw = payload.total;
  const amount =
    typeof totalRaw === "number"
      ? totalRaw
      : Number.parseFloat(String(totalRaw ?? "0")) || 0;
  const invDateRaw = payload.invoice_date;
  const invDate = typeof invDateRaw === "string" ? new Date(invDateRaw) : null;
  const daysOld =
    invDate && !Number.isNaN(invDate.getTime())
      ? Math.max(0, Math.round((Date.now() - invDate.getTime()) / 86_400_000))
      : undefined;
  const glCode = typeof payload.gl_code === "string" ? payload.gl_code : undefined;
  const country = typeof payload.vendor_country === "string"
    ? payload.vendor_country
    : typeof payload.country === "string" ? payload.country : undefined;
  return {
    vendor: vendorName,
    country,
    amount,
    glCode,
    status,
    invoiceNumber: typeof payload.invoice_number === "string" ? payload.invoice_number : undefined,
    daysOld,
  };
}

/**
 * Merge the AP pipeline's three function-as-schema emissions into one
 * record InvoiceHeroCard can consume. The extractor writes
 * ``app:emitted:invoice`` (vendor_name, invoice_number, line_items[],
 * subtotal, tax, total, ...); the validator writes
 * ``app:emitted:verdict`` (verdict, verdict_reason, routing,
 * escalation_assignee, sla_hours, audit_citations_csv); the poster
 * writes ``app:emitted:posting`` (gl_code, action). Validator/poster
 * fields are merged shallow into the invoice so the hero card's
 * verdict-footer band and metadata rows light up as the pipeline
 * progresses. Returns null when no extraction has happened yet.
 */
function mergeEmittedInvoicePayload(
  state: Record<string, unknown>,
): Record<string, unknown> | null {
  const invoice = state["app:emitted:invoice"];
  if (!invoice || typeof invoice !== "object" || Array.isArray(invoice)) {
    return null;
  }
  const merged: Record<string, unknown> = { ...(invoice as Record<string, unknown>) };
  const verdict = state["app:emitted:verdict"];
  if (verdict && typeof verdict === "object" && !Array.isArray(verdict)) {
    Object.assign(merged, verdict as Record<string, unknown>);
  }
  const posting = state["app:emitted:posting"];
  if (posting && typeof posting === "object" && !Array.isArray(posting)) {
    Object.assign(merged, posting as Record<string, unknown>);
  }
  return merged;
}

function APWorkbench({
  sessionId,
  onAction,
  dashboardOpen,
  dashboardInvoices,
  activeDocTab,
  sessionIdUrl,
  userUid,
  onSelectSession,
  onNewSession,
  onCloseDashboard,
  emittedInvoicePayload,
  onMcpUserIntent,
}: {
  sessionId: string | null;
  onAction?: (event: { actionName: string; context: Record<string, unknown> }) => void;
  dashboardOpen: boolean;
  dashboardInvoices: DashboardInvoice[];
  /** The currently-selected doc tab from the navbar (whichever the user
   * last clicked) — or null when no doc is open. Drives the Document
   * tab's content directly; the prior `viewMode === "side" | "focus"`
   * gating is dropped since the Workbench tab itself owns the layout. */
  activeDocTab: DocTabData | null;
  sessionIdUrl: string | null;
  userUid: string;
  onSelectSession: (sid: string) => void;
  onNewSession: () => void;
  onCloseDashboard: () => void;
  /** Merged canonical invoice payload synthesised from ADK session
   * state (``app:emitted:invoice`` + ``app:emitted:verdict`` +
   * ``app:emitted:posting``). This is the source the Invoice tab's
   * InvoiceHeroCard renders from — both live (refreshed after each
   * A2UI message arrives during a run) and on session resume.
   * Null when the pipeline hasn't produced an extraction yet. */
  emittedInvoicePayload: Record<string, unknown> | null;
  /** Click→chat handler fired when an MCP App artefact dispatches a
   * `user_intent` via `ui/update-model-context`. The page wires this
   * to sendMessage so the orchestrator receives the intent as a normal
   * chat turn. Threaded into both the KG and the Dashboard. */
  onMcpUserIntent?: (intent: string, context?: Record<string, unknown>) => void;
}) {
  const workspaceState = useSurfaceState("workspace");
  const [activeTab, setActiveTab] = useState<string>("invoice");
  const badges = useTabBadges();

  // Badge "Invoice" when the workspace surface receives content while
  // user is on a different tab.
  useEffect(() => {
    if (workspaceState?.surface && activeTab !== "invoice") {
      badges.mark("invoice");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceState?.surface, activeTab]);

  // Badge "Vendor" when the emit_* payload arrives (validator has run)
  // and the user is on a different tab.
  useEffect(() => {
    if (emittedInvoicePayload && activeTab !== "vendor") badges.mark("vendor");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emittedInvoicePayload, activeTab]);

  // Badge "Analytics" when show_ap_dashboard fires OR when a fresh
  // emit_* lands (auto-feed path), and we're not already viewing it.
  useEffect(() => {
    if ((dashboardOpen || emittedInvoicePayload) && activeTab !== "analytics") {
      badges.mark("analytics");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardOpen, emittedInvoicePayload, activeTab]);

  // Auto-switch to the Document tab when the user clicks a doc in the
  // navbar (activeDocTab.id changes). This is the simplification — the
  // prior side/focus/minimize viewMode dance is gone for AP, so a doc
  // click just opens the Document tab.
  const lastDocIdRef = useRef<string | null>(null);
  useEffect(() => {
    const nextId = activeDocTab?.id ?? null;
    if (nextId && nextId !== lastDocIdRef.current) {
      lastDocIdRef.current = nextId;
      setActiveTab("document");
      badges.clear("document");
    } else if (!nextId) {
      lastDocIdRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeDocTab?.id]);

  const tabs: WorkbenchTab[] = [
    {
      id: "invoice",
      eyebrow: "A2UI",
      label: "Invoice",
      badged: badges.isBadged("invoice"),
      content: (
        <div className="p-4">
          {emittedInvoicePayload ? (
            // The Invoice tab renders our canonical hero card driven
            // by the function-as-schema payload from ADK state, not
            // the A2UI workspace surface's display-shape dataModel
            // (flattened strings like "USD 800.00" + "3 line items —
            // Widget A ×10"). The A2UI surface keeps emitting on the
            // wire for protocol-purity / audit; we just don't render
            // it visually because the structured payload makes a
            // dramatically nicer card. A hidden A2UISurfaceMount
            // below preserves the action-button wiring (show_ap_dashboard)
            // without contributing visible chrome.
            <>
              <InvoiceHeroCard data={emittedInvoicePayload} />
              {workspaceState?.surface && (
                <div className="sr-only" aria-hidden>
                  <A2UISurfaceMount
                    surfaceId="workspace"
                    sessionId={sessionId}
                    onAction={onAction}
                  />
                </div>
              )}
            </>
          ) : workspaceState?.surface ? (
            // First-pass rendering before the extractor's emit_*
            // payload has been fetched. The A2UI workspace surface
            // arrives first via SSE and the canonical state fetch
            // catches up shortly after; until then this is the live
            // "watch it assemble" view.
            <A2UISurfaceMount
              surfaceId="workspace"
              className="h-full"
              sessionId={sessionId}
              onAction={onAction}
            />
          ) : (
            <EmptyTab
              title="No invoice yet"
              body="Drop or pick an invoice in the sidebar to run the pipeline. The extracted card will appear here as the agent emits it."
            />
          )}
        </div>
      ),
    },
    {
      id: "document",
      label: "Document",
      badged: badges.isBadged("document"),
      content: activeDocTab ? (
        <div className="flex h-full flex-col">
          <div className="min-h-0 flex-1 overflow-auto">
            <DocumentPanel docId={activeDocTab.id} />
          </div>
          <DocumentHistoryPanel
            documentId={activeDocTab.id}
            activeSessionId={sessionIdUrl}
            currentUserUid={userUid}
            onSelectSession={onSelectSession}
            onNewSession={onNewSession}
            onDeleteActive={onNewSession}
          />
        </div>
      ) : (
        <EmptyTab
          title="No document open"
          body="Click any uploaded document in the sidebar to view its parsed content here while the agent works on it."
        />
      ),
    },
    {
      id: "vendor",
      eyebrow: "MCP App",
      label: "Vendor",
      badged: badges.isBadged("vendor"),
      content: (
        <div className="h-full p-4">
          {emittedInvoicePayload ? (
            <VendorKgPanel
              payload={emittedInvoicePayload}
              onUserIntent={onMcpUserIntent}
            />
          ) : (
            <EmptyTab
              title="Vendor knowledge graph"
              body="Process an invoice — the vendor knowledge graph will populate with the validator's grounded references."
            />
          )}
        </div>
      ),
    },
    {
      id: "analytics",
      eyebrow: "MCP App",
      label: "Analytics",
      badged: badges.isBadged("analytics"),
      content: (
        <div className="h-full p-4">
          <APDashboardPanel
            onClose={dashboardOpen ? onCloseDashboard : undefined}
            // Prefer the action-driven dashboardInvoices payload when
            // present (orchestrator fired show_ap_dashboard with extra
            // context). Otherwise fall back to a synthetic single-row
            // entry derived from the current emit_* payload — so the
            // dashboard tab visibly reacts to every pipeline run even
            // when the agent didn't bother emitting the action.
            invoices={
              dashboardInvoices.length > 0
                ? dashboardInvoices
                : (() => {
                    const derived = dashboardInvoiceFromEmitted(emittedInvoicePayload);
                    return derived ? [derived] : undefined;
                  })()
            }
            replaceSeed={false}
            onUserIntent={onMcpUserIntent}
          />
        </div>
      ),
    },
  ];

  return (
    <Workbench
      tabs={tabs}
      activeTabId={activeTab}
      onActiveTabChange={(id) => {
        badges.clearOnActivate(id);
        setActiveTab(id);
      }}
      // Width scale: tight on laptops (~520px), comfortable on 1080p
      // (~600px), generous on ultrawide / 1440p+ (~720–820px) so the
      // hero card, KG graph, and dashboard donut all get room to breathe
      // instead of being pinned to the right edge.
      className="md:w-[520px] xl:w-[640px] 2xl:w-[760px] [@media(min-width:2000px)]:w-[860px]"
    />
  );
}

function EmptyTab({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-16 text-center">
      <h3 className="font-display text-lg font-semibold tracking-tight text-foreground">
        {title}
      </h3>
      <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">{body}</p>
    </div>
  );
}

function SidebarSurfaceRegion({ sessionId }: { sessionId: string | null }) {
  const state = useSurfaceState("sidebar");
  if (!state?.surface) return null;
  return (
    <div className="border-t px-2 py-2">
      <A2UISurfaceMount surfaceId="sidebar" sessionId={sessionId} />
    </div>
  );
}

function SectionChevron() {
  return (
    <svg
      className="h-3 w-3 shrink-0 transition-transform group-open:rotate-90"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  );
}

/**
 * Uniform collapsible sidebar section. Headers are always visible so the user
 * can reach every section regardless of which others are expanded; each body
 * is constrained so a single long section can't push others off-screen.
 */
function SidebarSection({
  title,
  defaultOpen = true,
  badge,
  action,
  bodyClassName,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group border-b border-border">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/60 hover:text-muted-foreground">
        <SectionChevron />
        <span className="flex-1 truncate">{title}</span>
        {badge}
        {action}
      </summary>
      <div className={bodyClassName ?? "px-3 pb-3 pt-1"}>{children}</div>
    </details>
  );
}

function ModalSurfaceRegion({ sessionId }: { sessionId: string | null }) {
  const state = useSurfaceState("modal");
  if (!state?.surface) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
      <div className="max-w-xl rounded-lg border bg-background p-4 shadow-xl">
        <A2UISurfaceMount surfaceId="modal" sessionId={sessionId} />
      </div>
    </div>
  );
}

/**
 * MULTI-SURFACE-A2UI M4 — wires the session-id transition to surface
 * lifecycle policy. When the user starts/switches sessions, session-scoped
 * surfaces (workspace, sidebar by default) clear automatically. The hook
 * is idempotent on the same sessionId so it won't fire on render.
 */
function SurfaceSessionLifecycle({ sessionId }: { sessionId: string | null }) {
  useClearSurfacesOnSessionChange(sessionId);
  return null;
}

export default function ChatPage({
  params,
}: {
  params: Promise<{ path: string[] }>;
}) {
  const { path } = use(params);
  const { user, loading } = useAuth();
  const router = useRouter();
  // Wait for auth to hydrate AND the user to be signed in before firing the
  // by-slug fetch. Without `user` in the gate, an unauth visitor would fire
  // a tokenless request, get 401, and see "Skill not found" before the
  // redirect to / kicks in.
  const { skillId, loading: resolving, notFound } = useSlugResolution(path, !loading && !!user);

  useEffect(() => {
    if (!loading && !user) router.replace("/");
  }, [loading, user, router]);

  if (loading || resolving) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;
  }
  if (!user) return null;
  if (notFound || !skillId) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
        <p>Skill not found.</p>
        <Link className="underline" href="/">Back to home</Link>
      </div>
    );
  }

  // path is validated by useSlugResolution; safe to construct the friendly prefix.
  const pathPrefix = `/chat/${path[0]}/${path[1]}`;

  return <ChatPageInner skillId={skillId} pathPrefix={pathPrefix} user={user} />;
}

function ChatPageInner({
  skillId,
  pathPrefix,
  user,
}: {
  skillId: string;
  pathPrefix: string;
  user: User;
}) {
  const searchParams = useSearchParams();
  const urlSessionId = searchParams.get("session");
  // chat-history-deep-fixes-2 Bug A': pre-allocate a stable threadId so the
  // URL-writeback effect after the first turn doesn't change AGUIProvider's
  // sessionId prop. Without this, useMemo([sessionId, …]) rebuilds the
  // HttpAgent the moment ?session= is written, agent.messages is destroyed,
  // and the user sees turn 1 vanish until the GET refills initialMessages.
  const stableThreadId = useStableThreadId(urlSessionId);

  return (
    <AGUIProvider skillId={skillId} sessionId={stableThreadId}>
      <ChatShell skillId={skillId} pathPrefix={pathPrefix} user={user} />
    </AGUIProvider>
  );
}

/**
 * Tiny caption that tells the user exactly which uploaded documents will
 * be sent on the next turn. Today the doc-tabs let users uncheck the
 * `included` box per tab; without an explicit "what's in context"
 * indicator, judges sometimes don't realise multi-doc state is in play
 * (e.g. uploaded three files but only two checked). This caption removes
 * the ambiguity — and stays out of the way when no doc is in context.
 */
function InContextBadge({
  openTabs,
  includedDocIds,
}: {
  openTabs: DocTabData[];
  includedDocIds: string[];
}) {
  if (includedDocIds.length === 0) return null;
  const includedTabs = openTabs.filter((t) => includedDocIds.includes(t.id));
  const label =
    includedTabs.length === 1
      ? `Will process: ${includedTabs[0].filename}`
      : `Will process ${includedTabs.length} documents on next turn`;
  return (
    <div className="mb-2 flex items-center gap-2 px-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
      <span className="h-1.5 w-1.5 rounded-full bg-primary/70" aria-hidden />
      <span className="truncate">{label}</span>
    </div>
  );
}

function StreamErrorBanner({
  error,
  onRetry,
  onDismiss,
}: {
  error: StreamError;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="inline-block max-w-[80%] space-y-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <p>{error.message}</p>
      <div className="flex gap-2">
        {error.retryable && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded border border-destructive/40 px-2 py-0.5 text-xs hover:bg-destructive/20"
          >
            Try again
          </button>
        )}
        <button
          type="button"
          onClick={onDismiss}
          className="rounded border border-destructive/20 px-2 py-0.5 text-xs text-destructive/70 hover:bg-destructive/10"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function ChatShell({
  skillId,
  pathPrefix,
  user,
}: {
  skillId: string;
  pathPrefix: string;
  user: User;
}) {
  const {
    sessionId: agentSessionId,
    messages,
    toolCalls,
    thinkingContent,
    isThinking,
    stageLabel,
    firedStages,
    stageStartTimes,
    sendMessage,
    isLoading,
    stalledMs,
    error,
    clearError,
    stop,
  } = useSkillAgent();
  const { displayName, mcpServerIds } = useSkillMeta(skillId);
  const { skills: userSkills, isLoading: skillsLoading } = useUserSkills(user.uid);
  const searchParams = useSearchParams();
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [showDocBrowser, setShowDocBrowser] = useState(true);
  const [openTabs, setOpenTabs] = useState<DocTabData[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  // Invoices pushed into APDashboardPanel — derived from session state's
  // ``app:emitted:invoice`` / ``app:emitted:verdict`` / ``app:emitted:posting``
  // keys (populated by the pipeline's emit_* FunctionTools). Without
  // this the dashboard renders only its hard-coded DEMO seed data
  // (the "is that real or placeholder?" question the user asked).
  const [dashboardInvoices, setDashboardInvoices] = useState<DashboardInvoice[]>([]);

  // Per-tab view mode lives on DocTabData ("minimized" | "side" | "focus").
  // Default: every newly opened tab starts minimised — chat keeps the full
  // width until the user picks a tab to expand. The doc-panel column width
  // (used when one tab is in "side" mode) is still persisted globally.
  const [docPanelWidthPx, setDocPanelWidthPx] = useState<number | null>(() => {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem("docPanelWidthPx");
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  });
  useEffect(() => {
    if (docPanelWidthPx !== null) localStorage.setItem("docPanelWidthPx", String(docPanelWidthPx));
  }, [docPanelWidthPx]);
  const docPanelRef = useRef<HTMLDivElement | null>(null);
  const startDocPanelResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = docPanelRef.current?.getBoundingClientRect().width ?? 0;
    const minWidth = 320;
    const maxWidth = window.innerWidth - 380;
    function onMove(ev: MouseEvent) {
      const next = Math.max(minWidth, Math.min(maxWidth, startWidth + (ev.clientX - startX)));
      setDocPanelWidthPx(next);
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);
  const [openInspectorKey, setOpenInspectorKey] = useState<SpecialistKey | null>(null);
  const lastUserMessageRef = useRef<string>("");

  // Session routing: read ?session= from URL, allow programmatic navigation
  const sessionId = searchParams.get("session");
  const { initialMessages, historyError, sessionGone } = useSessionMessages(sessionId);
  const { tabs: sessionDocTabs } = useSessionDocuments(sessionId);
  const { sessions, isLoading: sessionsLoading } = useSkillSessions(skillId);

  // Tracks whether the user reached this chat by clicking a conversation
  // thread (resume) vs starting a fresh chat. Backend uses this flag to
  // decide whether to eagerly inline document content into the LLM
  // request (resume → yes, fresh → standard tool-discovery flow).
  // Initial value: ?session= was already in the URL on mount = resume.
  // Updated by handleSelectSession (true) and handleNewSession (false);
  // intentionally NOT set by the URL-writeback effect that runs after a
  // fresh chat's first message — that's not a resume.
  const [enteredViaResume, setEnteredViaResume] = useState<boolean>(
    () => sessionId !== null,
  );

  // When the URL points at an existing session and we've resolved its
  // documentIds, mount those tabs (with `included: true`) so the user lands
  // on the same workspace they had during the original conversation. Only
  // fires once per session-load — `lastSyncedSessionId` ref guards against
  // wiping subsequent tab edits the user makes inside the same session.
  const lastSyncedSessionId = useRef<string | null>(null);
  useEffect(() => {
    if (!sessionId) {
      // Cleared back to a fresh chat — drop the ref so revisiting the same
      // session later still hydrates its tabs.
      lastSyncedSessionId.current = null;
      return;
    }
    if (sessionDocTabs === null) return;
    if (lastSyncedSessionId.current === sessionId) return;
    lastSyncedSessionId.current = sessionId;
    setOpenTabs(sessionDocTabs);
    setActiveTabId(sessionDocTabs[0]?.id ?? null);
  }, [sessionId, sessionDocTabs]);

  const navigateToSession = useCallback(
    (sid: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("session", sid);
      router.replace(`${pathPrefix}?${params.toString()}`);
    },
    [router, pathPrefix, searchParams],
  );

  // Pin the URL to the agent's session id once a fresh chat has produced its
  // first user message. Without this the ChatSessionIndex row exists in
  // Firestore but the URL never reflects it, so a refresh starts a new chat
  // and the existing session looks "lost". Skip when the URL already has a
  // session — the resume path is already pointing at the right id.
  useEffect(() => {
    if (!sessionId && agentSessionId && messages.length > 0) {
      navigateToSession(agentSessionId);
    }
  }, [sessionId, agentSessionId, messages.length, navigateToSession]);

  // Fire-and-forget bootstrap: pre-create the ChatSessionIndex + ADK session
  // before the first agent turn so iframe context pushes (ui/update-model-context)
  // that arrive immediately after mount don't 404. Idempotent on the backend —
  // resumed sessions already have an index and the call is a no-op.
  const bootstrappedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!agentSessionId || bootstrappedRef.current === agentSessionId) return;
    bootstrappedRef.current = agentSessionId;
    void fetchWithAuth(`/api/proxy/api/sessions/${agentSessionId}/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_id: skillId }),
    }).catch(() => {
      // bootstrap is best-effort; silently swallow errors so the chat isn't broken
    });
  }, [agentSessionId, skillId]);

  const activeSkill = userSkills.find((s) => s.skillId === skillId) ?? null;
  const activeSkillMeta = activeSkill ? getSkillMeta(activeSkill) : null;

  // Audit-View: derive per-specialist invocation state from the orchestrator's
  // toolCalls stream. Drives the chip row + InspectorPanel. When the audit-view
  // flag is off the state is computed but unused — cheap.
  const invocations = useSpecialistInvocations(
    toolCalls,
    sessionId ?? agentSessionId,
    stageStartTimes,
  );

  // Legacy URL redirect: if the user landed on /chat/{specialist-skill-id} and
  // the audit-view flag is on (and ?devmode=1 isn't set), bounce them to the
  // orchestrator chat with that specialist's chip pre-selected. Preserves
  // bookmarks/links from before the UX flip.
  const devmode = searchParams.get("devmode") === "1";
  useEffect(() => {
    if (!isAuditViewEnabled() || devmode || !activeSkillMeta) return;
    if (activeSkillMeta.role !== "specialist") return;
    const orchestrator = findSkillByMetaKey(userSkills, "orchestrator");
    if (!orchestrator) return;
    // Resolve the specialist key from the current skill's meta — matchKey
    // already returned "docparse" | "validator" | "poster".
    const key = (
      activeSkillMeta.tagline.toLowerCase().includes("document") ? "docparse" :
      activeSkillMeta.tagline.toLowerCase().includes("validator") ? "validator" :
      activeSkillMeta.tagline.toLowerCase().includes("poster") ? "poster" : null
    ) as SpecialistKey | null;
    const target = skillHref(orchestrator);
    const params = new URLSearchParams(searchParams.toString());
    if (sessionId) params.set("session", sessionId);
    const qs = params.toString();
    const hash = key ? `#audit=${key}` : "";
    router.replace(`${target}${qs ? `?${qs}` : ""}${hash}`);
  }, [activeSkillMeta, devmode, userSkills, router, searchParams, sessionId]);

  // Hash-driven chip auto-open: redirect lands with #audit={key}; pluck it
  // into openInspectorKey and clear the hash so a manual close stays closed.
  // Falls back to sessionStorage persistence (survives refresh).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const m = window.location.hash.match(/^#audit=(docparse|validator|poster)$/);
    if (m) {
      setOpenInspectorKey(m[1] as SpecialistKey);
      const url = new URL(window.location.href);
      url.hash = "";
      window.history.replaceState(null, "", url.toString());
      return;
    }
    const persisted = loadPersistedInspectorKey(sessionId ?? agentSessionId);
    if (persisted) setOpenInspectorKey(persisted);
    // Mount-once: dependencies intentionally empty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist open key whenever it changes so refresh keeps the inspector.
  useEffect(() => {
    persistInspectorKey(sessionId ?? agentSessionId, openInspectorKey);
  }, [openInspectorKey, sessionId, agentSessionId]);

  // Auto-close inspector when sidebar reopens and viewport is narrow, so the
  // panel doesn't overlap the doc list. Sidebar collapse happens elsewhere
  // (DocTabsBar toggle).
  useEffect(() => {
    if (openInspectorKey && showDocBrowser && typeof window !== "undefined" && window.innerWidth < 1100) {
      setShowDocBrowser(false);
    }
  }, [openInspectorKey, showDocBrowser]);

  const userInitial = (user.displayName ?? user.email ?? "U").charAt(0).toUpperCase();
  const userDisplayName = user.displayName ?? user.email ?? "You";
  // Google sign-in populates user.photoURL with the profile photo URL.
  // Local-mode / anonymous-group sessions leave it null and MessageBubble
  // falls back to the initial-chip avatar.
  const userPhotoURL = user.photoURL ?? null;

  // Documents currently included in agent context. Every open tab defaults to
  // included; users uncheck the box on a tab to exclude it without closing it.
  // Derivation extracted to lib/docContext.ts so the multi-doc contract is
  // unit-testable independently of the chat-page render tree
  // (multi-doc-context-fix.md / 1.22 D2).
  const includedDocIds = computeIncludedDocIds(openTabs);

  // Slug-driven branch points for the AP demo polish. The slug is the
  // last segment of the friendly URL (e.g. "ap-orchestrator"). For other
  // skills these flags are false and the chat behaves as before.
  const skillSlug = pathPrefix.split("/").pop() ?? "";
  const isApOrchestrator = skillSlug === "ap-orchestrator";
  const isFreshChat = messages.length === 0 && sessionId === null;
  const showSamplePicker = isApOrchestrator && isFreshChat && openTabs.length === 0;

  // Auto-collapse the sidebar on the user's first message in a fresh chat
  // so the chat + workbench own the screen during a run. Detected as the
  // isFreshChat → active transition. Re-opening the sidebar manually
  // mid-conversation won't be auto-closed again until a new fresh chat
  // starts (e.g. via "+ New"), so the rule is "auto-close once per
  // session-start." Resumed sessions land with isFreshChat already false
  // and never trigger this.
  const prevFreshChatRef = useRef(isFreshChat);
  useEffect(() => {
    if (prevFreshChatRef.current && !isFreshChat && !enteredViaResume) {
      setShowDocBrowser(false);
    }
    prevFreshChatRef.current = isFreshChat;
  }, [isFreshChat, enteredViaResume]);

  // Workbench Invoice tab is driven by the canonical emit_* payloads
  // from ADK state (`app:emitted:invoice` + verdict + posting), merged
  // into one record and passed to InvoiceHeroCard. The A2UI workspace
  // surface uses a flattened display shape ("USD 800.00", "3 line items —
  // Widget A ×10") which doesn't have line_items as an array; the
  // function-as-schema payloads do. So we render OUR hero card from
  // state, not from the SDK's A2uiSurface rendering of the surface model.
  //
  // Refresh trigger: every time the number of completed tool calls
  // ticks up. Each specialist's emit_* call increments the counter,
  // so the card progressively updates as Extract → Validate → Post
  // complete. Also fires on first mount when resuming a session
  // (toolCalls is empty but the persisted state still has emitted
  // payloads, so the initial fetch on session-id presence catches that).
  const [emittedInvoicePayload, setEmittedInvoicePayload] = useState<
    Record<string, unknown> | null
  >(null);
  // Per-specialist raw emissions kept SEPARATE (not merged) so the
  // audit view can show each specialist's distinct upstream input on
  // the Input side and its own emit on the Output side. Without this
  // split, every audit view would just show emit_*'s args on both
  // sides — looks identical across specialists and hides the data
  // handoff judges are trying to see.
  const [pipelineEmissions, setPipelineEmissions] = useState<{
    invoice: Record<string, unknown> | null;
    verdict: Record<string, unknown> | null;
    posting: Record<string, unknown> | null;
  }>({ invoice: null, verdict: null, posting: null });
  const completedToolCount = useMemo(
    () =>
      toolCalls.filter(
        (tc) => tc.status === "success" || tc.status === "error",
      ).length,
    [toolCalls],
  );
  useEffect(() => {
    if (!isApOrchestrator) return;
    const sid = sessionId ?? agentSessionId;
    if (!sid) return;
    void (async () => {
      try {
        const res = await fetchWithAuth(
          `/api/proxy/api/sessions/${encodeURIComponent(sid)}/state`,
        );
        if (!res.ok) return;
        const state = (await res.json()) as Record<string, unknown>;
        const merged = mergeEmittedInvoicePayload(state);
        if (merged) setEmittedInvoicePayload(merged);
        // Capture each emission separately for the audit-view input
        // handoff display. Missing fields → null (graceful).
        const asObj = (v: unknown): Record<string, unknown> | null =>
          v && typeof v === "object" && !Array.isArray(v)
            ? (v as Record<string, unknown>)
            : null;
        setPipelineEmissions({
          invoice: asObj(state["app:emitted:invoice"]),
          verdict: asObj(state["app:emitted:verdict"]),
          posting: asObj(state["app:emitted:posting"]),
        });
      } catch {
        // Network / parse errors are non-fatal — the workspace surface
        // fallback is still a valid view while the run is in flight.
      }
    })();
  }, [isApOrchestrator, sessionId, agentSessionId, completedToolCount]);

  // Clear the cached payload when the user starts a new session — old
  // session's card must not bleed into the fresh chat.
  useEffect(() => {
    if (isFreshChat) {
      setEmittedInvoicePayload(null);
      setPipelineEmissions({ invoice: null, verdict: null, posting: null });
    }
  }, [isFreshChat]);

  // ALSO clear on session-switch (URL `?session=` change, e.g. user
  // clicks a different session in the sidebar). Without this, the
  // workbench card and audit-view upstream-inputs keep showing the
  // PRIOR session's data until the new session's first emit_* lands —
  // visible as "I'm processing Nordic Parts but the right pane still
  // shows Acme GmbH" stale-render. isFreshChat doesn't fire here
  // because sessionId goes from oldId → newId without passing through
  // null. Tracked via a ref so we only clear on transitions, not on
  // every render.
  const prevSessionIdRef = useRef(sessionId);
  useEffect(() => {
    if (prevSessionIdRef.current !== sessionId) {
      setEmittedInvoicePayload(null);
      setPipelineEmissions({ invoice: null, verdict: null, posting: null });
      prevSessionIdRef.current = sessionId;
    }
  }, [sessionId]);

  async function handleSend() {
    const text = draft.trim();
    if (!text || isLoading || error) return;
    lastUserMessageRef.current = text;
    setDraft("");
    await sendMessage(text, {
      documentIds: includedDocIds,
      resumedSession: enteredViaResume,
    });
  }

  // MCP App click → chat. The user clicked an interactive surface
  // inside the KG or Dashboard iframe; the artefact pushed a
  // `user_intent` over `ui/update-model-context`; we route it through
  // the standard sendMessage path so the orchestrator answers in the
  // chat as if the user had typed it. Suppressed while a turn is in
  // flight (the chat input is disabled in that state — we silently
  // drop rather than queue, to match the typed-message behaviour).
  const handleMcpUserIntent = useCallback(
    (intent: string, _context?: Record<string, unknown>) => {
      if (isLoading || !intent.trim()) return;
      lastUserMessageRef.current = intent;
      void sendMessage(intent, {
        documentIds: includedDocIds,
        resumedSession: enteredViaResume,
      });
    },
    [isLoading, sendMessage, includedDocIds, enteredViaResume],
  );

  const handleRetry = useCallback(() => {
    const text = lastUserMessageRef.current;
    if (!text) { clearError(); return; }
    clearError();
    void sendMessage(text, {
      documentIds: includedDocIds,
      resumedSession: enteredViaResume,
    });
  }, [clearError, sendMessage, includedDocIds, enteredViaResume]);

  const handleAction = useCallback(
    (event: { actionName: string; context: Record<string, unknown> }) => {
      if (event.actionName === "show_ap_dashboard") {
        setDashboardOpen(true);
        const sid = sessionId ?? agentSessionId;
        if (sid) {
          // Read the current pipeline's emitted payloads from session
          // state and convert them to the dashboard's InvoiceData
          // shape. The dashboard's MCP artefact appends our entry on
          // top of its DEMO seed data so the user sees the invoice
          // they just processed *plus* the workshop context. Fail
          // silently — if the fetch errors the dashboard still
          // renders, just without the current invoice highlighted.
          void (async () => {
            try {
              const res = await fetchWithAuth(
                `/api/proxy/api/sessions/${encodeURIComponent(sid)}/state`,
              );
              if (!res.ok) return;
              const state = (await res.json()) as Record<string, unknown>;
              const invoice = state["app:emitted:invoice"] as
                | Record<string, unknown>
                | undefined;
              const verdict = state["app:emitted:verdict"] as
                | Record<string, unknown>
                | undefined;
              const posting = state["app:emitted:posting"] as
                | Record<string, unknown>
                | undefined;
              if (!invoice) {
                setDashboardInvoices([]);
                return;
              }
              const v = String(verdict?.verdict ?? "");
              const statusBucket: DashboardInvoice["status"] =
                v === "pass"
                  ? "approved"
                  : v === "needs_review"
                    ? "needs_review"
                    : "pending";
              const totalRaw = invoice.total;
              const amount =
                typeof totalRaw === "number"
                  ? totalRaw
                  : Number.parseFloat(String(totalRaw ?? "0")) || 0;
              const invDateRaw = invoice.invoice_date;
              const invDate =
                typeof invDateRaw === "string" ? new Date(invDateRaw) : null;
              const daysOld =
                invDate && !Number.isNaN(invDate.getTime())
                  ? Math.max(
                      0,
                      Math.round((Date.now() - invDate.getTime()) / 86_400_000),
                    )
                  : undefined;
              const current: DashboardInvoice = {
                vendor: String(invoice.vendor_name ?? "Unknown"),
                amount,
                glCode:
                  (posting?.ledger_account as string | undefined) ?? "Pending",
                status: statusBucket,
                invoiceNumber: String(invoice.invoice_number ?? ""),
                daysOld,
              };
              setDashboardInvoices([current]);
            } catch {
              // Network / parse errors are non-fatal — leave the
              // dashboard with its DEMO seed data so the user still
              // sees something useful.
              setDashboardInvoices([]);
            }
          })();
        }
        return;
      }
      void sendMessage(
        `[a2ui:${event.actionName}] ${JSON.stringify(event.context)}`,
        { documentIds: includedDocIds, resumedSession: enteredViaResume },
      );
    },
    [sendMessage, includedDocIds, enteredViaResume, sessionId, agentSessionId],
  );

  // Wraps navigateToSession with the resume signal so we differentiate
  // explicit thread clicks from the URL writeback that happens after a
  // fresh chat's first message.
  const handleSelectSession = useCallback(
    (sid: string) => {
      setEnteredViaResume(true);
      navigateToSession(sid);
    },
    [navigateToSession],
  );

  const handleNewSession = useCallback(() => {
    setEnteredViaResume(false);
    const params = new URLSearchParams(searchParams.toString());
    params.delete("session");
    const qs = params.toString();
    router.replace(qs ? `${pathPrefix}?${qs}` : pathPrefix);
  }, [router, pathPrefix, searchParams]);

  // Bring the user back to the "Start the demo" picker — the empty
  // state that greets visitors arriving from the homepage. Without
  // this, the only way to see the picker again is to navigate to the
  // homepage and re-click the demo link; clearing the URL session +
  // closing open doc tabs satisfies the SampleInvoicePicker's render
  // condition (`isApOrchestrator && isFreshChat && openTabs.length === 0`).
  // Tabs are closed BEFORE the new-session navigation so the React
  // state settles in one commit cycle and the picker shows immediately.
  const handleRestartDemo = useCallback(() => {
    setOpenTabs([]);
    setActiveTabId(null);
    setDashboardOpen(false);
    setDashboardInvoices([]);
    setEmittedInvoicePayload(null);
    setPipelineEmissions({ invoice: null, verdict: null, posting: null });
    handleNewSession();
  }, [handleNewSession]);

  // Defensive auto-clear: when ANY mutation site reports a deletion via the
  // sessions-changed bus and that id matches the URL session we're showing,
  // navigate to a fresh chat even if the originating handler missed the
  // active-session check (e.g. stale closure props on a detached panel).
  // See docs/design/v6.1.0/implemented/session-delete-ui.md.
  useEffect(() => {
    return subscribeSessionsChangedDetailed((detail) => {
      if (detail.deletedSessionId && detail.deletedSessionId === sessionId) {
        handleNewSession();
      }
    });
  }, [sessionId, handleNewSession]);

  // Stranded-session-prevention (1.23) Option 1: GET /messages returned 404,
  // meaning ?session=X points at a session the backend no longer has. Drop
  // ?session= from the URL so useStableThreadId mints a fresh UUID before
  // the next outbound POST. One-shot — handleNewSession clears sessionId,
  // which resets sessionGone via the hook on the next effect cycle.
  useEffect(() => {
    if (sessionGone && sessionId) {
      handleNewSession();
    }
  }, [sessionGone, sessionId, handleNewSession]);

  const handleDeleteSkillSession = useCallback(
    async (sid: string) => {
      // Mirrors DocumentHistoryPanel.handleDelete: confirm + DELETE +
      // dispatch sessions-changed (which both useSkillSessions and any
      // mounted useDocumentSessions listen for, so both panels reconcile)
      // + clear URL if the deleted session is active.
      if (
        !window.confirm(
          "Delete this conversation? This can't be undone from the UI.",
        )
      ) {
        return;
      }
      try {
        const res = await fetchWithAuth(
          `/api/proxy/api/sessions/${encodeURIComponent(sid)}`,
          { method: "DELETE" },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        notifySessionsChanged({ deletedSessionId: sid });
        if (sid === sessionId) {
          handleNewSession();
        }
      } catch {
        // Backend rejected. Reconcile via the same bus.
        notifySessionsChanged();
      }
    },
    [sessionId, handleNewSession],
  );

  const handleDocClick = useCallback((doc: ParsedDocument) => {
    setOpenTabs((prev) => {
      if (prev.find((t) => t.id === doc.id)) return prev;
      const tab: DocTabData = {
        id: doc.id,
        filename: doc.originalFilename,
        format: doc.sourceFormat,
        included: true,
        // Default minimised — opening a doc adds a tab but doesn't steal the
        // viewport. User clicks the panel/fullscreen icon on the tab to view.
        viewMode: "minimized",
        parseStatus: doc.parseStatus,
        blockCount: doc.blockCount ?? null,
        createdAt: doc.createdAt,
      };
      // AP single-doc invariant: the orchestrator's pipeline processes one
      // invoice per turn, so opening a second doc on AP would just confuse
      // the extractor (which doc is "this invoice"?). Replace the tabs
      // rather than appending so includedDocIds is always at most one.
      if (isApOrchestrator) return [tab];
      return [...prev, tab];
    });
    setActiveTabId(doc.id);
  }, [isApOrchestrator]);

  // Wired to UploadDropZone.onUploadComplete and SampleInvoicePicker.
  // Adds a minimal tab (full metadata fills in on the next DocListView
  // refresh) and, when the chat is a fresh ap-orchestrator session,
  // immediately fires "Process this invoice" so judges don't need a
  // second click. Mid-conversation uploads stay manual — re-deriving
  // isFreshChat at call time means the second upload after a completed
  // run never auto-sends.
  const handleDocReady = useCallback(
    (docId: string, filename: string) => {
      const ext = filename.split(".").pop()?.toLowerCase() ?? "";
      setOpenTabs((prev) => {
        const newTab: DocTabData = {
          id: docId,
          filename,
          format: ext,
          included: true,
          viewMode: "minimized",
        };
        // AP single-doc invariant — see handleDocClick. Importing a new
        // invoice replaces whatever was open so the pipeline always
        // processes exactly one doc per turn.
        if (isApOrchestrator) return [newTab];
        if (prev.find((t) => t.id === docId)) {
          return prev.map((t) =>
            t.id === docId ? { ...t, included: true } : t,
          );
        }
        return [...prev, newTab];
      });
      setActiveTabId(docId);

      const shouldAutoProcess =
        isApOrchestrator &&
        messages.length === 0 &&
        sessionId === null &&
        !isLoading;
      if (shouldAutoProcess) {
        lastUserMessageRef.current = "Process this invoice";
        void sendMessage("Process this invoice", {
          documentIds: [docId],
          resumedSession: false,
        });
      }
    },
    [isApOrchestrator, messages.length, sessionId, isLoading, sendMessage],
  );

  const handleTabClose = useCallback((id: string) => {
    setOpenTabs((prev) => {
      const next = prev.filter((t) => t.id !== id);
      if (activeTabId === id) setActiveTabId(next[next.length - 1]?.id ?? null);
      return next;
    });
  }, [activeTabId]);

  const handleTabToggleInclude = useCallback((id: string) => {
    setOpenTabs((prev) =>
      prev.map((t) => (t.id === id ? { ...t, included: !t.included } : t)),
    );
  }, []);

  // Mutually-exclusive expand: setting one tab to side/focus minimises any
  // other tab that was previously expanded. Setting to "minimized" doesn't
  // touch the others.
  const handleSetTabViewMode = useCallback(
    (id: string, mode: "minimized" | "side" | "focus") => {
      setOpenTabs((prev) =>
        prev.map((t) => {
          if (t.id === id) return { ...t, viewMode: mode };
          if (mode !== "minimized" && t.viewMode !== "minimized") {
            return { ...t, viewMode: "minimized" };
          }
          return t;
        }),
      );
      if (mode !== "minimized") setActiveTabId(id);
    },
    [],
  );

  // The single tab (if any) whose panel is currently rendered.
  const expandedTab = openTabs.find((t) => t.viewMode !== "minimized") ?? null;

  const inputDisabled = isLoading || error !== null;

  // Esc cancels an in-flight run — perceived-snappiness affordance from
  // ttft-instrumentation.md M2. Bound at document level because the
  // text input is disabled while isLoading (no keydown fires there).
  // No-op when no run is in flight; lets browser handle Esc otherwise.
  useEffect(() => {
    if (!isLoading) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        stop();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isLoading, stop]);

  return (
    <SurfaceRegistryProvider>
    <SurfaceSessionLifecycle sessionId={sessionId} />
    <main className="flex h-screen flex-col bg-background">
      <SkillsBar
        skills={userSkills}
        activeSkillId={skillId}
        isLoading={skillsLoading}
        onCreateClick={() => router.push("/skills/new")}
        invocations={invocations}
        openInspectorKey={openInspectorKey}
        onChipSelect={(key) =>
          setOpenInspectorKey((cur) => (cur === key ? null : key))
        }
      />

      <DocTabsBar
        tabs={openTabs}
        activeTabId={activeTabId}
        showBrowser={showDocBrowser}
        onSelect={setActiveTabId}
        onClose={handleTabClose}
        onToggleInclude={handleTabToggleInclude}
        onToggleBrowser={() => setShowDocBrowser((v) => !v)}
        onSetViewMode={handleSetTabViewMode}
        hideViewModeButtons={isApOrchestrator}
      />

      <div className="flex min-h-0 flex-1">
        {showDocBrowser && (
          <aside className="flex w-72 shrink-0 flex-col overflow-y-auto border-r border-border bg-background">
            {activeSkillMeta && (
              <SidebarSection title="Skill" defaultOpen bodyClassName="px-3 pb-3 pt-1">
                <div className="mb-1.5 flex items-center gap-2">
                  <span className="shrink-0 text-primary">{activeSkillMeta.icon}</span>
                  <span className="truncate text-xs font-semibold text-foreground">{activeSkillMeta.tagline}</span>
                  {activeSkillMeta.isEntryPoint && (
                    <span className="shrink-0 rounded-full bg-primary/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary">
                      Hub
                    </span>
                  )}
                </div>
                <p className="text-[10px] leading-relaxed text-muted-foreground">{activeSkillMeta.description}</p>
                {activeSkillMeta.subAgentCount && (
                  <div className="mt-2 flex gap-1.5">
                    <span className="rounded-full border border-primary/20 bg-primary/8 px-2 py-0.5 text-[9px] font-semibold text-primary/70">
                      {activeSkillMeta.subAgentCount} sub-agents
                    </span>
                  </div>
                )}
              </SidebarSection>
            )}

            <SidebarSection
              title="Sessions"
              defaultOpen={false}
              badge={
                sessions.length > 0 ? (
                  <span className="rounded-full bg-muted px-1.5 py-0.5 text-[9px] font-semibold text-muted-foreground">
                    {sessions.length}
                  </span>
                ) : null
              }
              action={
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleNewSession();
                  }}
                  title="New conversation"
                  className="rounded-full border border-primary/20 bg-primary/8 px-2 py-0.5 text-[9px] font-semibold text-primary/70 transition-colors hover:bg-primary/15 hover:text-primary"
                >
                  + New
                </button>
              }
              bodyClassName="px-3 pb-2"
            >
              <div className="max-h-48 overflow-y-auto">
                <SkillSessionPanel
                  sessions={sessions}
                  activeSessionId={sessionId}
                  isLoading={sessionsLoading}
                  onSelectSession={handleSelectSession}
                  onDelete={(sid) => void handleDeleteSkillSession(sid)}
                />
              </div>
            </SidebarSection>

            <SidebarSection title="Import from GCS bucket" defaultOpen={false} bodyClassName="">
              <GCSFileBrowser skillId={skillId} />
            </SidebarSection>

            <SidebarSection title="My Documents" defaultOpen={false} bodyClassName="">
              <div className="flex max-h-[40vh] flex-col overflow-hidden">
                <DocListView uid={user.uid} onDocClick={handleDocClick} />
              </div>
            </SidebarSection>

            <SidebarSection
              title="Upload from your computer"
              defaultOpen={isApOrchestrator}
              bodyClassName=""
            >
              <UploadDropZone skillId={skillId} onUploadComplete={handleDocReady} />
            </SidebarSection>

            {/* MULTI-SURFACE-A2UI M3: sidebar surface mount — only visible
                when agent populates the surface. */}
            <SidebarSurfaceRegion sessionId={sessionId ?? agentSessionId} />
          </aside>
        )}

        {!isApOrchestrator && expandedTab && (
          <>
            <div
              ref={docPanelRef}
              className="flex shrink-0 flex-col overflow-hidden border-r"
              style={{
                width:
                  expandedTab.viewMode === "focus"
                    ? "80%"
                    : docPanelWidthPx !== null
                      ? `${docPanelWidthPx}px`
                      : "50%",
              }}
            >
              <div className="min-h-0 flex-1 overflow-auto">
                <DocumentPanel docId={expandedTab.id} />
              </div>
              <DocumentHistoryPanel
                documentId={expandedTab.id}
                activeSessionId={sessionId}
                currentUserUid={user.uid}
                onSelectSession={handleSelectSession}
                onNewSession={handleNewSession}
                onDeleteActive={handleNewSession}
              />
            </div>
            {expandedTab.viewMode === "side" && (
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize document panel"
                onMouseDown={startDocPanelResize}
                onDoubleClick={() => setDocPanelWidthPx(null)}
                title="Drag to resize · double-click to reset"
                className="group relative w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/40"
              >
                <div className="absolute inset-y-0 -left-1 -right-1" />
              </div>
            )}
          </>
        )}

        {/* MULTI-SURFACE-A2UI M3: workspace surface mount — non-AP legacy slot. */}
        {!isApOrchestrator && !expandedTab && (
          <WorkspaceSurfaceRegion sessionId={sessionId ?? agentSessionId} onAction={handleAction} />
        )}

        {/* M5: AP analytics dashboard — legacy non-AP path. */}
        {!isApOrchestrator && !expandedTab && dashboardOpen && (
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r md:max-w-xl">
            <APDashboardPanel
              onClose={() => setDashboardOpen(false)}
              invoices={dashboardInvoices.length > 0 ? dashboardInvoices : undefined}
              replaceSeed={false}
            />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          {showSamplePicker && (
            <div className="border-b border-border bg-background/50">
              <SampleInvoicePicker
                skillId={skillId}
                onSampleSelected={handleDocReady}
              />
            </div>
          )}
          {/* Restart-demo affordance — visible whenever the AP demo is
              past the start state (session active OR a doc tab is open).
              Click clears tabs + state + the URL session so the
              SampleInvoicePicker reappears. Avoids the "I have to go
              back to the homepage to pick another sample" UX trap. */}
          {isApOrchestrator && !showSamplePicker && (
            <div className="flex shrink-0 items-center justify-end border-b border-border bg-background/40 px-3 py-1.5">
              <button
                type="button"
                onClick={handleRestartDemo}
                disabled={isLoading}
                title="Clear the conversation and return to the sample picker"
                className="group inline-flex items-center gap-1.5 rounded-md border border-border/60 bg-background px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border/60 disabled:hover:bg-background disabled:hover:text-muted-foreground"
              >
                <svg
                  className="h-3 w-3 transition-transform duration-500 ease-out group-hover:-rotate-180"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  aria-hidden="true"
                >
                  <path d="M3 8a5 5 0 0 1 9-3l1.5-1.5M13 8a5 5 0 0 1-9 3L2.5 12.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M11 3.5h2.5V6M5 12.5H2.5V10" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Restart demo
              </button>
            </div>
          )}
          <ChatMessageList
            messages={messages}
            // initialMessages are the persisted history fetched by
            // useSessionMessages(sessionId). They're only relevant when the
            // user RESUMED an existing session — in that case the live
            // `messages` array is empty until the first new turn, so the
            // history fills the gap. When the URL is written back mid-chat
            // (fresh chat → server assigns sessionId → URL update), the
            // history fetch returns the same messages that are ALREADY in
            // live `messages` — duplicating every bubble. `enteredViaResume`
            // distinguishes the two cases.
            initialMessages={enteredViaResume ? initialMessages : undefined}
            historyError={historyError}
            toolCalls={toolCalls}
            thinkingContent={thinkingContent}
            isThinking={isThinking}
            isLoading={isLoading}
            error={error}
            skillId={displayName}
            userInitial={userInitial}
            userDisplayName={userDisplayName}
            userPhotoURL={userPhotoURL}
            stageLabel={stageLabel}
            firedStages={firedStages}
            stalledMs={stalledMs}
            onAction={handleAction}
            mcpServerIds={mcpServerIds}
            sessionId={sessionId ?? agentSessionId}
            onChatMessage={(text) => {
              // MCP App iframe → notification adapter → synthetic chat
              // turn. Goes out as a normal sendMessage (with the same
              // doc-context + resume flags as a typed message).
              void sendMessage(text, {
                documentIds: includedDocIds,
                resumedSession: enteredViaResume,
              });
            }}
            errorBanner={
              error ? (
                <StreamErrorBanner
                  error={error}
                  onRetry={handleRetry}
                  onDismiss={clearError}
                />
              ) : undefined
            }
          />

          <footer className="border-t border-border bg-background p-3">
            <InContextBadge openTabs={openTabs} includedDocIds={includedDocIds} />
            <form
              className="flex items-center gap-2 rounded-xl border border-border bg-muted/40 px-3 py-2 transition-all focus-within:border-primary/40 focus-within:shadow-[0_0_0_1px_rgba(232,168,0,0.12)] dark:border-white/[0.09] dark:bg-white/[0.04]"
              onSubmit={(e) => {
                e.preventDefault();
                void handleSend();
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Describe an invoice or ask a question…"
                className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
                disabled={inputDisabled}
              />
              {isLoading ? (
                <button
                  type="button"
                  onClick={stop}
                  className="shrink-0 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:border-white/20 hover:text-foreground"
                >
                  ■ Stop
                </button>
              ) : (
                <button
                  type="submit"
                  className="shrink-0 rounded-lg bg-primary px-4 py-1.5 text-xs font-bold text-primary-foreground shadow-[0_0_8px_rgba(232,168,0,0.2)] transition-all hover:shadow-[0_0_14px_rgba(232,168,0,0.35)] disabled:opacity-40 disabled:shadow-none"
                  disabled={!draft.trim() || inputDisabled}
                >
                  Send →
                </button>
              )}
            </form>
          </footer>
        </div>

        {/* Workbench — persistent tabbed pane. Replaces the prior conditional
            ladder (DocumentPanel ⊕ WorkspaceSurface ⊕ Globe ⊕ Dashboard, only
            one renders at a time). All four tabs stay mounted so MCP App
            iframes don't remount on every switch. Only active on ap-orchestrator;
            other skills fall through to legacy behavior. Rendered after the
            chat column so it sits on the right edge with the chat as the
            primary conversational column on the left. */}
        {isApOrchestrator && (
          <APWorkbench
            sessionId={sessionId ?? agentSessionId}
            onAction={handleAction}
            dashboardOpen={dashboardOpen}
            dashboardInvoices={dashboardInvoices}
            activeDocTab={
              openTabs.find((t) => t.id === activeTabId) ?? null
            }
            sessionIdUrl={sessionId}
            userUid={user.uid}
            onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
            onCloseDashboard={() => setDashboardOpen(false)}
            emittedInvoicePayload={emittedInvoicePayload}
            onMcpUserIntent={handleMcpUserIntent}
          />
        )}
      </div>
      <LatencyHUD />
      {/* AUDIT-VIEW M1: persistent right-side inspector panel for the
          selected specialist. Open via SpecialistChip click; close via ✕,
          ESC, or clicking the same chip again. */}
      <InspectorPanel
        open={openInspectorKey !== null}
        specialistKey={openInspectorKey}
        state={openInspectorKey ? invocations[openInspectorKey] : null}
        onClose={() => setOpenInspectorKey(null)}
        skills={userSkills}
        sessionId={sessionId ?? agentSessionId}
        uid={user.uid}
        onMcpUserIntent={handleMcpUserIntent}
        pipelineEmissions={pipelineEmissions}
        openDocs={openTabs}
      />
      {/* MULTI-SURFACE-A2UI M3: modal surface mount — fixed-position
          overlay at page root. Only visible when populated; M4 will wire
          the user-gesture guard so the agent can't pop one unprompted. */}
      <ModalSurfaceRegion sessionId={sessionId ?? agentSessionId} />
      <BrandFooter variant="slim" />
    </main>
    </SurfaceRegistryProvider>
  );
}
