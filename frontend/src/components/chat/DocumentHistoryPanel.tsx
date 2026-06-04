"use client";

import { useState } from "react";
import { type SessionFilter, useDocumentSessions } from "@/hooks/useDocumentSessions";
import type { ChatSessionSummary } from "@/hooks/useDocumentSessions";
import { fetchWithAuth } from "@/lib/apiClient";
import { notifySessionsChanged } from "@/lib/sessionEvents";

export interface DocumentHistoryPanelProps {
  documentId: string;
  activeSessionId: string | null;
  currentUserUid: string;
  onSelectSession: (sessionId: string, ownerUid: string) => void;
  onNewSession: () => void;
  /** Called when the user deletes the currently-active session — lets
   * the parent clear the URL ?session= so the chat surface resets to
   * a fresh state (same code path as "+ New conversation"). */
  onDeleteActive?: () => void;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface SessionRowProps {
  session: ChatSessionSummary;
  isActive: boolean;
  isOwner: boolean;
  onClick: () => void;
  onRename: (newTitle: string) => Promise<void>;
  /** Owner-only delete affordance. When omitted, no trash icon is shown
   * (used for non-owner team rows). */
  onDelete?: () => void;
}

function SessionRow({ session, isActive, isOwner, onClick, onRename, onDelete }: SessionRowProps) {
  const initialTitle = session.title ?? "Untitled conversation";
  const time = relativeTime(session.last_message_at);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(initialTitle);
  const [saving, setSaving] = useState(false);

  async function commit() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === initialTitle) {
      setIsEditing(false);
      setDraft(initialTitle);
      return;
    }
    setSaving(true);
    try {
      await onRename(trimmed);
      setIsEditing(false);
    } catch {
      // Revert; the parent's refetch will resync if the request actually
      // succeeded but raised on a transient.
      setDraft(initialTitle);
      setIsEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (isEditing) {
    return (
      <div
        className={[
          "w-full rounded border px-3 py-2 text-sm",
          isActive ? "border-primary/40 bg-primary/5" : "border-border bg-muted/30",
        ].join(" ")}
      >
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void commit();
            } else if (e.key === "Escape") {
              setDraft(initialTitle);
              setIsEditing(false);
            }
          }}
          disabled={saving}
          className="w-full bg-transparent font-medium text-foreground outline-none"
          aria-label="Rename conversation"
        />
        <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
          {time} · {session.turn_count} turn{session.turn_count !== 1 ? "s" : ""}
        </div>
      </div>
    );
  }

  return (
    <div
      className={[
        "group flex w-full items-center gap-1 rounded border px-3 py-1.5 text-sm transition-colors",
        isActive
          ? "border-primary/40 bg-primary/5 text-foreground"
          : "border-transparent text-muted-foreground hover:bg-muted/30 hover:text-foreground",
      ].join(" ")}
    >
      <button onClick={onClick} className="min-w-0 flex-1 text-left">
        <div className="truncate text-xs font-medium">{initialTitle}</div>
        <div className="mt-0.5 font-mono text-[10px] text-muted-foreground/70">
          {time} · {session.turn_count} turn{session.turn_count !== 1 ? "s" : ""}
        </div>
      </button>
      {isOwner && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setDraft(initialTitle);
            setIsEditing(true);
          }}
          aria-label={`Rename ${initialTitle}`}
          title="Rename"
          className="shrink-0 rounded p-1 text-muted-foreground/60 opacity-0 transition-colors hover:bg-muted hover:text-foreground group-hover:opacity-100"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M11 2l3 3-7 7H4v-3l7-7z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      {isOwner && onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label={`Delete ${initialTitle}`}
          title="Delete"
          className="shrink-0 rounded p-1 text-muted-foreground/60 opacity-0 transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M3 4h10M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4M7 4V3a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v1" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
    </div>
  );
}

async function renameSession(sessionId: string, title: string): Promise<void> {
  const res = await fetchWithAuth(
    `/api/proxy/api/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetchWithAuth(
    `/api/proxy/api/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export default function DocumentHistoryPanel({
  documentId,
  activeSessionId,
  currentUserUid,
  onSelectSession,
  onNewSession,
  onDeleteActive,
}: DocumentHistoryPanelProps) {
  // Default COLLAPSED so the document is the primary thing on screen.
  // The earlier default (open) made the history list dominate the
  // pane on docs used across many sessions — see "template-level
  // issue" note for upstream feedback to sunholo-data/ai-protocol-platform.
  const [isOpen, setIsOpen] = useState(false);
  // refetch is exposed by the hook but unused here — cross-panel sync is
  // handled via the sessions-changed event bus, which the hook subscribes
  // to itself.
  const { sessions, isLoading, error } = useDocumentSessions(documentId);
  const totalCount = sessions.length;

  const mine = sessions.filter((s) => s.owner_uid === currentUserUid);
  const team = sessions.filter((s) => s.owner_uid !== currentUserUid);

  async function handleRename(sessionId: string, title: string): Promise<void> {
    await renameSession(sessionId, title);
    // Both the skill-level panel and any other doc panel showing this
    // session's title need to update — the bus fans this out.
    notifySessionsChanged();
  }

  async function handleDelete(sessionId: string): Promise<void> {
    // Soft-delete on the backend (archivedAt). Confirm dialog gates the
    // destructive action; backend stays the single source of truth so a
    // network failure here is fully recoverable (the row reappears on the
    // next refetch). See docs/design/v6.1.0/session-delete-ui.md.
    if (
      !window.confirm(
        "Delete this conversation? This can't be undone from the UI.",
      )
    ) {
      return;
    }
    try {
      await deleteSession(sessionId);
      notifySessionsChanged({ deletedSessionId: sessionId });
      if (sessionId === activeSessionId) {
        onDeleteActive?.();
      }
    } catch {
      // Backend rejected. Refetch reconciles any partial state — if the
      // row is still there the user sees it return.
      notifySessionsChanged();
    }
  }

  return (
    <div className="shrink-0 border-t border-border bg-background">
      {/* Header — always visible, collapsible. Counter badge so the user
          sees the history exists without having to expand it. */}
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
        aria-expanded={isOpen}
      >
        <span className="flex items-center gap-2 font-mono uppercase tracking-wider">
          Conversations
          {totalCount > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
              {totalCount}
            </span>
          )}
        </span>
        <span className="text-muted-foreground/50">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        // Cap the open list at ~25vh so the parent DocumentPanel stays
        // the primary thing on screen even when a doc has hundreds of
        // sessions tied to it. Internal scroll handles the overflow.
        <div className="max-h-[25vh] space-y-3 overflow-y-auto border-t border-border px-3 pb-3 pt-2">
          {isLoading && (
            <p className="px-1 text-xs text-muted-foreground">Loading…</p>
          )}
          {error && (
            <p className="px-1 text-xs text-destructive">{error}</p>
          )}

          {!error && (
            <div>
              <p className="mb-1 px-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                Mine
              </p>
              {mine.length === 0 && !isLoading && (
                <p className="px-1 text-xs text-muted-foreground/60">No conversations yet</p>
              )}
              <div className="space-y-1">
                {mine.map((s) => (
                  <SessionRow
                    key={s.session_id}
                    session={s}
                    isActive={s.session_id === activeSessionId}
                    isOwner={true}
                    onClick={() => onSelectSession(s.session_id, s.owner_uid)}
                    onRename={(t) => handleRename(s.session_id, t)}
                    onDelete={() => void handleDelete(s.session_id)}
                  />
                ))}
              </div>
            </div>
          )}

          {!error && team.length > 0 && (
            <div>
              <p className="mb-1 px-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                Team
              </p>
              <div className="space-y-1">
                {team.map((s) => (
                  <SessionRow
                    key={s.session_id}
                    session={s}
                    isOwner={false}
                    onRename={async () => {}}
                    isActive={s.session_id === activeSessionId}
                    onClick={() => onSelectSession(s.session_id, s.owner_uid)}
                  />
                ))}
              </div>
            </div>
          )}

          <button
            onClick={onNewSession}
            className="w-full rounded px-3 py-1.5 text-left text-xs font-medium text-primary transition-colors hover:bg-primary/5"
          >
            + New conversation
          </button>
        </div>
      )}
    </div>
  );
}
