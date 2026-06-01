"use client";

import { useRef } from "react";
import { DocTab, type DocTabData } from "./DocTab";

interface DocTabsBarProps {
  tabs: DocTabData[];
  activeTabId: string | null;
  showBrowser: boolean;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onToggleInclude: (id: string) => void;
  onToggleBrowser: () => void;
}

export function DocTabsBar({
  tabs,
  activeTabId,
  showBrowser,
  onSelect,
  onClose,
  onToggleInclude,
  onToggleBrowser,
}: DocTabsBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex items-stretch border-b bg-muted/30">
      {/* Browser toggle */}
      <button
        type="button"
        onClick={onToggleBrowser}
        className={[
          "shrink-0 border-r px-2 text-muted-foreground hover:bg-accent",
          showBrowser ? "bg-accent/50" : "",
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
          <span className="flex items-center px-3 text-xs text-muted-foreground">
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

    </div>
  );
}
