"use client";

// APDashboardPanel — shows the AP analytics dashboard MCP artefact.
// Triggered by the ap-orchestrator's A2UI "show_ap_dashboard" button action
// or mounted persistently for the ap-orchestrator skill.

import { useCallback, useEffect, useRef, useState } from "react";
import { StaticArtefactFrame, type StaticArtefactFrameHandle } from "./StaticArtefactFrame";

const SANDBOX_URL =
  process.env.NEXT_PUBLIC_MCP_SANDBOX_URL?.replace(/\/$/, "") ?? "";

export interface InvoiceData {
  vendor: string;
  country?: string;
  amount: number;
  glCode?: string;
  daysOld?: number;
  status?: "approved" | "needs_review" | "exception" | "pending";
  invoiceNumber?: string;
}

interface APDashboardPanelProps {
  /** Invoice data to push into the dashboard. */
  invoices?: InvoiceData[];
  /**
   * When ``true`` (default), the supplied invoices REPLACE the
   * dashboard artefact's DEMO seed data. When ``false`` the
   * invoices are MERGED into the seed data (one
   * ``ui/update-data`` per invoice, no reset) — useful when the
   * caller has the current session's invoice but wants the seed
   * data to remain as workshop context (so charts don't look
   * sparse with a single real entry). Default ``true`` matches
   * the pre-2026-06-03 behaviour.
   */
  replaceSeed?: boolean;
  onClose?: () => void;
}

export function APDashboardPanel({ invoices, replaceSeed = true, onClose }: APDashboardPanelProps) {
  const frameRef = useRef<StaticArtefactFrameHandle>(null);
  const [ready, setReady] = useState(false);

  const handleModelContext = useCallback((_sc: Record<string, unknown>) => {
    // Dashboard doesn't push model context back in this implementation
  }, []);

  const handleInitialized = useCallback(() => {
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready || !frameRef.current) return;
    if (!invoices || invoices.length === 0) return;
    if (replaceSeed) {
      frameRef.current.sendNotification("ui/update-data", {
        reset: true,
        invoices,
      });
    } else {
      // Merge mode: push each invoice as a single-row update so the
      // artefact's handler (which dedupes by vendor+invoiceNumber)
      // adds them on top of its DEMO seed data instead of wiping it.
      for (const inv of invoices) {
        frameRef.current.sendNotification("ui/update-data", { invoice: inv });
      }
    }
  }, [ready, invoices, replaceSeed]);

  if (!SANDBOX_URL) return null;

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border bg-background shadow-xl" style={{ height: 420 }}>
      <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">AP Analytics</span>
          {invoices && invoices.length > 0 && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {invoices.length} invoice{invoices.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Close AP dashboard"
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round"/>
            </svg>
          </button>
        )}
      </div>
      <div className="relative flex-1 overflow-hidden">
        {!ready && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        )}
        <StaticArtefactFrame
          ref={frameRef}
          sandboxOrigin={SANDBOX_URL}
          artefactPath="ap-dashboard"
          onUpdateModelContext={handleModelContext}
          onInitialized={handleInitialized}
          hostContext={{ theme: "dark", displayMode: "inline" }}
          className="h-full w-full"
          title="AP Analytics Dashboard"
        />
      </div>
    </div>
  );
}
