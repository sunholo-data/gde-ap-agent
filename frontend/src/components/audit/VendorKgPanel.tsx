"use client";

// VendorKgPanel — mounts the ap-vendor-kg MCP App inside the validator
// Audit View. Pushes the validator's most recent citations + grounded
// vendor record into the widget so judges can SEE the protocol stack
// (AG-UI events → A2UI surfaces → MCP App iframe) on a single specialist.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  StaticArtefactFrame,
  type StaticArtefactFrameHandle,
} from "@/components/workspace/StaticArtefactFrame";

const SANDBOX_URL =
  process.env.NEXT_PUBLIC_MCP_SANDBOX_URL?.replace(/\/$/, "") ?? "";

interface VendorKgPanelProps {
  /** Most recent validator result JSON (resultContent). Used to extract
   * citations + vendor/PO/duplicate references for the widget.
   */
  resultJson: string | undefined;
}

interface KgUpdate {
  reset?: boolean;
  vendor?: Partial<{ name: string; id: string; country: string; approved: boolean; status: string }>;
  po?: { ref: string; total?: number; currency?: string };
  priorInvoices?: Array<{ id: string; amount?: number; currency?: string }>;
  thisInvoice?: { number?: string; amount?: number; currency?: string };
  citations?: string[];
}

export function VendorKgPanel({ resultJson }: VendorKgPanelProps) {
  const frameRef = useRef<StaticArtefactFrameHandle>(null);
  const [ready, setReady] = useState(false);

  const update = useMemo<KgUpdate | null>(() => buildUpdate(resultJson), [resultJson]);

  const handleModelContext = useCallback((_sc: Record<string, unknown>) => {}, []);
  const handleInitialized = useCallback(() => setReady(true), []);

  useEffect(() => {
    if (!ready || !frameRef.current || !update) return;
    frameRef.current.sendNotification("ui/update-data", { reset: true, ...update });
  }, [ready, update]);

  if (!SANDBOX_URL) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-3 text-[10px] text-muted-foreground">
        Vendor KG widget unavailable — <code>NEXT_PUBLIC_MCP_SANDBOX_URL</code> is not configured.
      </div>
    );
  }

  return (
    <div
      className="flex flex-col overflow-hidden rounded-md border border-border bg-background"
      style={{ height: 320 }}
      data-testid="audit-vendor-kg"
    >
      <div className="relative flex-1 overflow-hidden">
        {!ready && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        )}
        <StaticArtefactFrame
          ref={frameRef}
          sandboxOrigin={SANDBOX_URL}
          artefactPath="ap-vendor-kg"
          onUpdateModelContext={handleModelContext}
          onInitialized={handleInitialized}
          hostContext={{ theme: "dark", displayMode: "inline" }}
          className="h-full w-full"
          title="Vendor Knowledge Graph"
        />
      </div>
    </div>
  );
}

/**
 * Best-effort extract: the validator emits a free-form JSON with
 * verdict/reasons/citations. The KG widget seeds a stylised default,
 * so a partial extract is fine — missing fields keep their seed.
 */
function buildUpdate(resultJson: string | undefined): KgUpdate | null {
  if (!resultJson) return null;
  try {
    const v = JSON.parse(resultJson) as Record<string, unknown>;
    const update: KgUpdate = {};
    if (Array.isArray(v.citations)) {
      update.citations = (v.citations as unknown[]).map((c) => String(c)).slice(0, 8);
    }
    const reasons = Array.isArray(v.reasons) ? (v.reasons as Array<Record<string, unknown>>) : [];
    const vendorReason = reasons.find((r) => String(r.check ?? "").toLowerCase().includes("vendor"));
    if (vendorReason) {
      update.vendor = {
        approved: String(vendorReason.severity ?? "").toLowerCase() !== "fail",
        status: String(vendorReason.detail ?? "checked"),
      };
    }
    // The validator might pass through the upstream extracted invoice
    // under an `invoice` key (audit-view paths) — use it when present.
    const invoice = v.invoice as Record<string, unknown> | undefined;
    if (invoice) {
      update.vendor = {
        ...update.vendor,
        name: typeof invoice.vendor_name === "string" ? invoice.vendor_name : undefined,
        id: typeof invoice.vendor_id === "string" ? invoice.vendor_id : undefined,
      };
      if (typeof invoice.po_reference === "string") {
        update.po = {
          ref: invoice.po_reference,
          total: typeof invoice.total === "number" ? invoice.total : undefined,
          currency: typeof invoice.currency === "string" ? invoice.currency : undefined,
        };
      }
      update.thisInvoice = {
        number: typeof invoice.invoice_number === "string" ? invoice.invoice_number : undefined,
        amount: typeof invoice.total === "number" ? invoice.total : undefined,
        currency: typeof invoice.currency === "string" ? invoice.currency : undefined,
      };
    }
    return update;
  } catch {
    return null;
  }
}
