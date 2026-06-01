"use client";

// VendorGlobePanel — shows the vendor-globe MCP App artefact in a slide-up panel.
// Triggered by the ap-orchestrator's A2UI "show_vendor_globe" button action.
// Uses StaticArtefactFrame to load the globe artefact from the MCP sandbox,
// then pushes vendor data to it via sendNotification.

import { useCallback, useEffect, useRef, useState } from "react";
import { StaticArtefactFrame, type StaticArtefactFrameHandle } from "./StaticArtefactFrame";

const SANDBOX_URL =
  process.env.NEXT_PUBLIC_MCP_SANDBOX_URL?.replace(/\/$/, "") ?? "";

interface VendorGlobePanelProps {
  /** Vendor name extracted from the invoice */
  vendor: string;
  /** Vendor country (name or ISO code) */
  country: string;
  /** Invoice total amount */
  amount?: number;
  onClose: () => void;
}

export function VendorGlobePanel({ vendor, country, amount, onClose }: VendorGlobePanelProps) {
  const frameRef = useRef<StaticArtefactFrameHandle>(null);
  const [ready, setReady] = useState(false);

  const handleModelContext = useCallback((_sc: Record<string, unknown>) => {
    // Globe doesn't push model context back to the host in this implementation
  }, []);

  const handleInitialized = useCallback(() => {
    setReady(true);
  }, []);

  // Push vendor data once the artefact signals ready
  useEffect(() => {
    if (!ready || !frameRef.current) return;
    frameRef.current.sendNotification("ui/update-data", {
      vendor,
      country,
      amount: amount ?? 0,
      originLabel: "London HQ",
    });
  }, [ready, vendor, country, amount]);

  if (!SANDBOX_URL) return null;

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border bg-background shadow-xl" style={{ height: 420 }}>
      <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">Vendor Location</span>
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">{vendor}</span>
          <span className="text-xs text-muted-foreground">{country}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Close vendor globe"
        >
          <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round"/>
          </svg>
        </button>
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
          artefactPath="vendor-globe"
          onUpdateModelContext={handleModelContext}
          onInitialized={handleInitialized}
          hostContext={{ theme: "dark", displayMode: "inline" }}
          className="h-full w-full"
          title="Vendor geography globe"
        />
      </div>
    </div>
  );
}
