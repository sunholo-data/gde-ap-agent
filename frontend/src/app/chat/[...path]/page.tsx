"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import type { DocTabData } from "@/components/doc-browser/DocTab";
import { DocListView } from "@/components/doc-browser/DocListView";
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
import { AGUIProvider } from "@/providers/AGUIProvider";
import {
  SurfaceRegistryProvider,
  useClearSurfacesOnSessionChange,
  useSurfaceState,
} from "@/providers/SurfaceRegistry";
import { A2UISurfaceMount } from "@/components/protocols/A2UISurfaceMount";
import { DocumentPanel } from "@/components/document/DocumentPanel";
import { LatencyHUD } from "@/components/dev/LatencyHUD";
import { VendorGlobePanel } from "@/components/workspace/VendorGlobePanel";
import { APDashboardPanel } from "@/components/workspace/APDashboardPanel";

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
function WorkspaceSurfaceRegion({ sessionId }: { sessionId: string | null }) {
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
        />
      </div>
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
    sendMessage,
    isLoading,
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
  const [globeContext, setGlobeContext] = useState<{ vendor: string; country: string; amount?: number } | null>(null);
  const [dashboardOpen, setDashboardOpen] = useState(false);
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

  const userInitial = (user.displayName ?? user.email ?? "U").charAt(0).toUpperCase();
  const userDisplayName = user.displayName ?? user.email ?? "You";

  // Documents currently included in agent context. Every open tab defaults to
  // included; users uncheck the box on a tab to exclude it without closing it.
  // Derivation extracted to lib/docContext.ts so the multi-doc contract is
  // unit-testable independently of the chat-page render tree
  // (multi-doc-context-fix.md / 1.22 D2).
  const includedDocIds = computeIncludedDocIds(openTabs);

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
      if (event.actionName === "show_vendor_globe") {
        setGlobeContext({
          vendor: String(event.context.vendor ?? ""),
          country: String(event.context.country ?? ""),
          amount: typeof event.context.amount === "number" ? event.context.amount : undefined,
        });
        return;
      }
      if (event.actionName === "show_ap_dashboard") {
        setDashboardOpen(true);
        return;
      }
      void sendMessage(
        `[a2ui:${event.actionName}] ${JSON.stringify(event.context)}`,
        { documentIds: includedDocIds, resumedSession: enteredViaResume },
      );
    },
    [sendMessage, includedDocIds, enteredViaResume],
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
      return [
        ...prev,
        { id: doc.id, filename: doc.originalFilename, format: doc.sourceFormat, included: true },
      ];
    });
    setActiveTabId(doc.id);
  }, []);

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
    <main className="flex h-screen flex-col bg-[hsl(222,47%,5%)]">
      <SkillsBar
        skills={userSkills}
        activeSkillId={skillId}
        isLoading={skillsLoading}
        onCreateClick={() => router.push("/skills/new")}
      />

      <DocTabsBar
        tabs={openTabs}
        activeTabId={activeTabId}
        showBrowser={showDocBrowser}
        onSelect={setActiveTabId}
        onClose={handleTabClose}
        onToggleInclude={handleTabToggleInclude}
        onToggleBrowser={() => setShowDocBrowser((v) => !v)}
      />

      <div className="flex min-h-0 flex-1">
        {showDocBrowser && (
          <aside className="flex w-64 shrink-0 flex-col overflow-hidden border-r border-white/[0.07] bg-[hsl(222,47%,4%)]">
            <div className="border-b border-white/[0.06] px-3 py-2.5">
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/50">Sessions</p>
              <div className="mt-1.5 max-h-40 overflow-y-auto">
                <SkillSessionPanel
                  sessions={sessions}
                  activeSessionId={sessionId}
                  isLoading={sessionsLoading}
                  onSelectSession={handleSelectSession}
                  onDelete={(sid) => void handleDeleteSkillSession(sid)}
                />
              </div>
            </div>
            <DocListView uid={user.uid} onDocClick={handleDocClick} />
            <div className="border-t">
              <UploadDropZone skillId={skillId} />
            </div>
            {/* MULTI-SURFACE-A2UI M3: sidebar surface mount — only visible
                when agent populates the surface. Sits below the doc list +
                upload zone so it doesn't disturb the existing sidebar UX. */}
            <SidebarSurfaceRegion sessionId={sessionId ?? agentSessionId} />
          </aside>
        )}

        {activeTabId && (
          <div className="flex w-1/2 shrink-0 flex-col overflow-hidden border-r">
            <div className="min-h-0 flex-1 overflow-auto">
              <DocumentPanel docId={activeTabId} />
            </div>
            <DocumentHistoryPanel
              documentId={activeTabId}
              activeSessionId={sessionId}
              currentUserUid={user.uid}
              onSelectSession={handleSelectSession}
              onNewSession={handleNewSession}
              onDeleteActive={handleNewSession}
            />
          </div>
        )}

        {/* MULTI-SURFACE-A2UI M3: workspace surface mount — takes the
            doc-panel slot when no doc tab is active AND the agent has
            published a workspace tree. Hidden in both other cases. */}
        {!activeTabId && !globeContext && (
          <WorkspaceSurfaceRegion sessionId={sessionId ?? agentSessionId} />
        )}

        {/* M4: Vendor globe — shown when ap-orchestrator fires show_vendor_globe */}
        {!activeTabId && globeContext && !dashboardOpen && (
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r md:max-w-xl">
            <VendorGlobePanel
              vendor={globeContext.vendor}
              country={globeContext.country}
              amount={globeContext.amount}
              onClose={() => setGlobeContext(null)}
            />
          </div>
        )}

        {/* M5: AP analytics dashboard — shown when show_ap_dashboard fires */}
        {!activeTabId && dashboardOpen && (
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r md:max-w-xl">
            <APDashboardPanel onClose={() => setDashboardOpen(false)} />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
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
            stageLabel={stageLabel}
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

          <footer className="border-t border-white/[0.07] bg-[hsl(222,47%,4%)] p-3">
            <form
              className="flex items-center gap-2 rounded-xl border border-white/[0.09] bg-white/[0.04] px-3 py-2 transition-all focus-within:border-primary/40 focus-within:shadow-[0_0_0_1px_rgba(232,168,0,0.12)]"
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
      </div>
      <LatencyHUD />
      {/* MULTI-SURFACE-A2UI M3: modal surface mount — fixed-position
          overlay at page root. Only visible when populated; M4 will wire
          the user-gesture guard so the agent can't pop one unprompted. */}
      <ModalSurfaceRegion sessionId={sessionId ?? agentSessionId} />
    </main>
    </SurfaceRegistryProvider>
  );
}
