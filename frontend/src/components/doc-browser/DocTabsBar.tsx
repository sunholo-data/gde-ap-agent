"use client";

import { useRef } from "react";
import { DocTab, type DocTabData } from "./DocTab";

export type DocPanelMode = "side" | "focus" | "collapsed";

interface DocTabsBarProps {
  tabs: DocTabData[];
  activeTabId: string | null;
  showBrowser: boolean;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onToggleInclude: (id: string) => void;
  onToggleBrowser: () => void;
  docPanelMode?: DocPanelMode;
  onSetDocPanelMode?: (mode: DocPanelMode) => void;
}

function ModeButton({
  active,
  title,
  onClick,
  children,
}: {
  active: boolean;
  title: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={active}
      className={[
        "flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground",
        active ? "bg-white/[0.08] text-foreground" : "",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function DocTabsBar({
  tabs,
  activeTabId,
  showBrowser,
  onSelect,
  onClose,
  onToggleInclude,
  onToggleBrowser,
  docPanelMode,
  onSetDocPanelMode,
}: DocTabsBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const showModeControls = !!onSetDocPanelMode && tabs.length > 0;

  return (
    <div className="flex items-stretch border-b border-border bg-background">
      {/* Browser toggle */}
      <button
        type="button"
        onClick={onToggleBrowser}
        className={[
          "shrink-0 border-r border-white/[0.07] px-2.5 text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground",
          showBrowser ? "bg-white/[0.05] text-foreground" : "",
        ].join(" ")}
        title={showBrowser ? "Hide document list" : "Show document list"}
        aria-label="Toggle document list"
      >
        <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <rect x="1.5" y="2" width="5" height="12" rx="1" />
          <path d="M9 4h5M9 8h5M9 12h3" strokeLinecap="round" />
        </svg>
      </button>

      {/* Tab strip — horizontally scrollable, no scrollbar */}
      <div
        ref={scrollRef}
        role="tablist"
        className="flex min-w-0 flex-1 overflow-x-auto"
        style={{ scrollbarWidth: "none" }}
      >
        {tabs.length === 0 && (
          <span className="flex items-center px-3 text-xs text-muted-foreground/50">
            No open documents
          </span>
        )}
        {tabs.map((tab) => (
          <DocTab
            key={tab.id}
            tab={tab}
            isActive={tab.id === activeTabId}
            onSelect={onSelect}
            onClose={onClose}
            onToggleInclude={onToggleInclude}
          />
        ))}
      </div>

      {/* Doc-panel view-mode controls — appear once a doc is open */}
      {showModeControls && (
        <div className="flex shrink-0 items-center gap-0.5 border-l border-white/[0.07] px-1">
          <ModeButton
            active={docPanelMode === "side"}
            title="Side-by-side (split view)"
            onClick={() => onSetDocPanelMode!("side")}
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
              <rect x="2" y="3" width="5.2" height="10" rx="0.8" />
              <rect x="8.8" y="3" width="5.2" height="10" rx="0.8" />
            </svg>
          </ModeButton>
          <ModeButton
            active={docPanelMode === "focus"}
            title="Focus mode (doc takes most of the width)"
            onClick={() => onSetDocPanelMode!("focus")}
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
              <rect x="2" y="3" width="9" height="10" rx="0.8" />
              <rect x="12.2" y="3" width="1.8" height="10" rx="0.5" />
            </svg>
          </ModeButton>
          <ModeButton
            active={docPanelMode === "collapsed"}
            title="Collapse doc panel (tabs only)"
            onClick={() => onSetDocPanelMode!("collapsed")}
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="2" y="3" width="12" height="2.5" rx="0.6" />
              <path d="M8 13l-2.2-2.2M8 13l2.2-2.2" />
            </svg>
          </ModeButton>
        </div>
      )}
    </div>
  );
}
