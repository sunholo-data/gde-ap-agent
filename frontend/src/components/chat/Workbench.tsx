"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Workbench — persistent tabbed pane that replaces the prior single-slot
 * conditional ladder in the chat page (DocumentPanel ⊕ WorkspaceSurface
 * ⊕ Globe ⊕ Dashboard).
 *
 * Design intent: at any moment, the user can flip between the Invoice
 * card, the Document view, the Vendor knowledge surface, and the
 * Analytics dashboard without losing state. Inactive tabs stay mounted
 * (just `hidden`) so MCP App iframes don't remount and re-handshake on
 * every switch.
 *
 * Tab badges: pass `badged` true to indicate "new content arrived while
 * this tab was inactive". The badge clears the moment the tab is
 * activated. The parent owns badging state.
 */

export interface WorkbenchTab {
  /** Stable id matching what `activeTabId` references. */
  id: string;
  /** Short label shown on the tab itself. */
  label: string;
  /** Optional eyebrow rendered above the label (e.g. "MCP App"). */
  eyebrow?: string;
  /** When true a small primary-dot appears, meaning "new content here". */
  badged?: boolean;
  /** Optional disabled state — render greyed out, unclickable. */
  disabled?: boolean;
  /** The tab body. Always rendered; visibility-toggled by `hidden` class. */
  content: React.ReactNode;
}

interface WorkbenchProps {
  tabs: WorkbenchTab[];
  /** Controlled active-tab id. Pass-through to parent so external events
   * (e.g. agent emitting a surface_action) can set the active tab. */
  activeTabId: string;
  onActiveTabChange: (id: string) => void;
  className?: string;
}

export function Workbench({
  tabs,
  activeTabId,
  onActiveTabChange,
  className,
}: WorkbenchProps) {
  const tabListRef = useRef<HTMLDivElement | null>(null);

  // Keyboard navigation (Left/Right) — accessible-by-default tab strip.
  useEffect(() => {
    const el = tabListRef.current;
    if (!el) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const idx = tabs.findIndex((t) => t.id === activeTabId);
      if (idx === -1) return;
      const dir = e.key === "ArrowRight" ? 1 : -1;
      // Skip disabled tabs.
      for (let i = 1; i <= tabs.length; i++) {
        const next = tabs[(idx + dir * i + tabs.length) % tabs.length];
        if (!next.disabled) {
          onActiveTabChange(next.id);
          return;
        }
      }
    }
    el.addEventListener("keydown", onKey);
    return () => el.removeEventListener("keydown", onKey);
  }, [tabs, activeTabId, onActiveTabChange]);

  return (
    <div className={cn("flex min-w-0 flex-1 flex-col overflow-hidden border-r border-border bg-background", className)}>
      <header className="flex items-stretch border-b border-border bg-muted/10">
        <div className="flex items-center gap-3 border-r border-border px-4">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Workbench
          </span>
        </div>
        <div
          ref={tabListRef}
          role="tablist"
          aria-label="Workbench tabs"
          className="flex flex-1 overflow-x-auto"
        >
          {tabs.map((tab) => {
            const isActive = tab.id === activeTabId;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`workbench-panel-${tab.id}`}
                tabIndex={isActive ? 0 : -1}
                disabled={tab.disabled}
                onClick={() => onActiveTabChange(tab.id)}
                className={cn(
                  "group relative flex shrink-0 items-baseline gap-2 px-4 py-3 text-left transition-colors",
                  isActive
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                  tab.disabled && "cursor-not-allowed opacity-40 hover:text-muted-foreground",
                )}
              >
                {tab.eyebrow && (
                  <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground/70">
                    {tab.eyebrow}
                  </span>
                )}
                <span className="font-display text-sm font-semibold tracking-tight">
                  {tab.label}
                </span>
                {tab.badged && !isActive && (
                  <span
                    aria-label="new content"
                    className="ml-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
                  />
                )}
                {isActive && (
                  <span
                    aria-hidden
                    className="absolute inset-x-2 -bottom-px h-0.5 rounded-t-sm bg-primary"
                  />
                )}
              </button>
            );
          })}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <div
              key={tab.id}
              role="tabpanel"
              id={`workbench-panel-${tab.id}`}
              aria-hidden={!isActive}
              className={cn(
                "h-full w-full overflow-auto",
                !isActive && "hidden",
              )}
            >
              {tab.content}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Convenience hook: tracks which inactive tabs have "received content
 * since they were last seen" so the parent can pass `badged` flags.
 *
 * Usage:
 *   const { mark, isBadged, clearOnActivate } = useTabBadges();
 *   useEffect(() => { if (newInvoiceArrived) mark("invoice"); }, [...]);
 *   <Workbench tabs={[{ id: 'invoice', badged: isBadged('invoice'), ... }]} ... />
 *   <Workbench activeTabId={current} onActiveTabChange={(id) => { clearOnActivate(id); setCurrent(id); }} ... />
 */
export function useTabBadges() {
  const [badged, setBadged] = useState<Record<string, boolean>>({});
  return {
    mark: (id: string) => setBadged((p) => ({ ...p, [id]: true })),
    clear: (id: string) => setBadged((p) => ({ ...p, [id]: false })),
    clearOnActivate: (id: string) =>
      setBadged((p) => (p[id] ? { ...p, [id]: false } : p)),
    isBadged: (id: string) => Boolean(badged[id]),
  };
}
