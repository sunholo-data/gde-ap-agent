"use client";

const FORMAT_COLORS: Record<string, string> = {
  pdf: "bg-red-100 text-red-700",
  docx: "bg-blue-100 text-blue-700",
  pptx: "bg-orange-100 text-orange-700",
  xlsx: "bg-green-100 text-green-700",
  csv: "bg-green-100 text-green-700",
  md: "bg-purple-100 text-purple-700",
};

export type DocTabViewMode = "minimized" | "side" | "focus";

export interface DocTabData {
  id: string;
  filename: string;
  format: string;
  /** Whether this doc is sent to the agent on the next turn. Defaults to true on open. */
  included: boolean;
  /** How this tab's document is displayed. Defaults to "minimized" — the tab
   * exists but the doc-panel column is hidden. Setting one tab to "side" or
   * "focus" minimises any other expanded tab (one expanded doc at a time). */
  viewMode: DocTabViewMode;
  // --- Tooltip metadata (best-effort; may be absent for restored tabs) ---
  parseStatus?: string;
  blockCount?: number | null;
  createdAt?: string;
}

interface DocTabProps {
  tab: DocTabData;
  isActive: boolean;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onToggleInclude: (id: string) => void;
  onSetViewMode: (id: string, mode: DocTabViewMode) => void;
}

function formatRelative(iso?: string): string | null {
  if (!iso) return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  const diffMs = Date.now() - ts;
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function buildTooltip(tab: DocTabData): string {
  const lines: string[] = [tab.filename];
  const meta: string[] = [];
  if (tab.format) meta.push(tab.format.toUpperCase());
  if (tab.parseStatus) meta.push(tab.parseStatus);
  if (typeof tab.blockCount === "number") meta.push(`${tab.blockCount} blocks`);
  if (meta.length) lines.push(meta.join(" · "));
  const rel = formatRelative(tab.createdAt);
  if (rel) lines.push(`uploaded ${rel}`);
  return lines.join("\n");
}

function PanelIcon({ active }: { active: boolean }) {
  // Two side-by-side rectangles; the left one is highlighted when active.
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <rect x="2" y="3" width="5.2" height="10" rx="0.6" fill={active ? "currentColor" : "none"} fillOpacity={active ? 0.18 : 0} />
      <rect x="8.8" y="3" width="5.2" height="10" rx="0.6" />
    </svg>
  );
}

function FocusIcon({ active }: { active: boolean }) {
  // Maximised: one wide rectangle, one thin strip.
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <rect x="2" y="3" width="9.2" height="10" rx="0.6" fill={active ? "currentColor" : "none"} fillOpacity={active ? 0.18 : 0} />
      <rect x="12.4" y="3" width="1.6" height="10" rx="0.4" />
    </svg>
  );
}

function MinimizeIcon({ active }: { active: boolean }) {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="3" width="12" height="2.5" rx="0.6" fill={active ? "currentColor" : "none"} fillOpacity={active ? 0.18 : 0} />
      <path d="M8 13l-2.2-2.2M8 13l2.2-2.2" />
    </svg>
  );
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
      title={title}
      aria-label={title}
      aria-pressed={active}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={[
        "flex h-5 w-5 shrink-0 items-center justify-center rounded transition-colors",
        active
          ? "bg-primary/15 text-primary"
          : "text-muted-foreground/70 hover:bg-accent hover:text-foreground",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function DocTab({
  tab,
  isActive,
  onSelect,
  onClose,
  onToggleInclude,
  onSetViewMode,
}: DocTabProps) {
  const fmtColor =
    FORMAT_COLORS[tab.format.toLowerCase()] ?? "bg-muted text-muted-foreground";
  const includeLabel = tab.included
    ? `Exclude ${tab.filename} from agent context`
    : `Include ${tab.filename} in agent context`;
  const tooltip = buildTooltip(tab);

  return (
    <div
      role="tab"
      aria-selected={isActive}
      title={tooltip}
      className={[
        "group flex shrink-0 cursor-pointer items-center gap-1.5 border-b-2 px-2.5 py-1.5 text-xs",
        isActive
          ? "border-primary bg-background text-foreground"
          : "border-transparent text-muted-foreground hover:bg-accent hover:text-foreground",
        tab.included ? "" : "opacity-60",
      ].join(" ")}
      onClick={() => onSelect(tab.id)}
    >
      {/* Include-in-context checkbox */}
      <button
        type="button"
        role="checkbox"
        aria-checked={tab.included}
        aria-label={includeLabel}
        title={includeLabel}
        onClick={(e) => {
          e.stopPropagation();
          onToggleInclude(tab.id);
        }}
        className={[
          "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border",
          tab.included
            ? "border-primary bg-primary text-primary-foreground"
            : "border-muted-foreground/40 bg-transparent",
        ].join(" ")}
      >
        {tab.included && (
          <svg className="h-2.5 w-2.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M2 6.5l2.5 2.5L10 3.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>

      {tab.format && (
        <span className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-medium uppercase ${fmtColor}`}>
          {tab.format}
        </span>
      )}

      <span className="max-w-[140px] truncate">{tab.filename}</span>

      {/* View-mode controls — one tab can be expanded at a time. */}
      <div className="ml-1 flex items-center gap-0.5">
        <ModeButton
          active={tab.viewMode === "side"}
          title={`Show ${tab.filename} in side panel`}
          onClick={() => onSetViewMode(tab.id, "side")}
        >
          <PanelIcon active={tab.viewMode === "side"} />
        </ModeButton>
        <ModeButton
          active={tab.viewMode === "focus"}
          title={`Show ${tab.filename} fullscreen`}
          onClick={() => onSetViewMode(tab.id, "focus")}
        >
          <FocusIcon active={tab.viewMode === "focus"} />
        </ModeButton>
        <ModeButton
          active={tab.viewMode === "minimized"}
          title={`Minimise ${tab.filename}`}
          onClick={() => onSetViewMode(tab.id, "minimized")}
        >
          <MinimizeIcon active={tab.viewMode === "minimized"} />
        </ModeButton>
      </div>

      <button
        type="button"
        aria-label={`Close ${tab.filename}`}
        title={`Close ${tab.filename}`}
        onClick={(e) => {
          e.stopPropagation();
          onClose(tab.id);
        }}
        className="ml-0.5 rounded p-0.5 opacity-0 hover:bg-muted group-hover:opacity-100"
      >
        <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M2 2l8 8M10 2l-8 8" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}
