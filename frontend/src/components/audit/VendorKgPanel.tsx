"use client";

// VendorKgPanel — mounts the ap-vendor-kg MCP App.
//
// Two mount sites:
//   - Validator audit view (InspectorPanel) — receives the raw validator
//     resultContent JSON string via `resultJson`.
//   - Workbench Vendor tab — receives the merged emit_* payload
//     (invoice + verdict + posting fields, already parsed) via `payload`.
//
// `payload` takes precedence over `resultJson` when both are passed.
// `buildUpdate` defensively pulls fields from either shape so the
// artefact gets the richest possible seed for its graph + citations.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  StaticArtefactFrame,
  type StaticArtefactFrameHandle,
} from "@/components/workspace/StaticArtefactFrame";
import { extractUserIntent } from "@/lib/mcpUserIntent";

const SANDBOX_URL =
  process.env.NEXT_PUBLIC_MCP_SANDBOX_URL?.replace(/\/$/, "") ?? "";

interface VendorKgPanelProps {
  /** Validator result JSON string (audit-view path). Lower-precedence
   * input — passed through JSON.parse and merged with whatever `payload`
   * provides. */
  resultJson?: string;
  /** Pre-parsed payload (workbench path). Higher precedence — preferred
   * source when present. Typically the merged emit_invoice + verdict +
   * posting record produced by the AP pipeline. */
  payload?: Record<string, unknown> | null;
  /** Fixed-height container override (px). When unset, the panel fills
   * its parent (`h-full`) with a 360px floor — preferred for the
   * workbench mount where the tab content provides the height bound.
   * The audit view passes an explicit height because it sits in a
   * scrollable inspector panel where `h-full` would resolve to zero. */
  height?: number;
  /** Optional user-intent handler. The artefact dispatches click events
   * via ``ui/update-model-context`` with a fork-side ``user_intent``
   * convention; when set, this callback fires with the natural-language
   * intent string so the host can auto-send it as a chat message. */
  onUserIntent?: (intent: string, context?: Record<string, unknown>) => void;
  /** Which ADK agent last touched the payload. The artefact uses this
   * to show a "Updated by Validator · just now" attribution chip, so
   * the demo audience sees that the iframe is reactive to agent state
   * rather than rendering a static template. */
  source?: string;
}

interface KgUpdate {
  reset?: boolean;
  vendor?: Partial<{ name: string; id: string; country: string; approved: boolean; status: string }>;
  po?: { ref: string; total?: number; currency?: string };
  priorInvoices?: Array<{ id: string; amount?: number; currency?: string }>;
  thisInvoice?: { number?: string; amount?: number; currency?: string };
  citations?: string[];
}

export function VendorKgPanel({ resultJson, payload, height, onUserIntent, source }: VendorKgPanelProps) {
  const frameRef = useRef<StaticArtefactFrameHandle>(null);
  const [ready, setReady] = useState(false);

  const update = useMemo<KgUpdate | null>(() => buildUpdate(payload, resultJson), [payload, resultJson]);

  const handleModelContext = useCallback(
    (sc: Record<string, unknown>) => {
      const intentMsg = extractUserIntent(sc);
      if (intentMsg && onUserIntent) {
        onUserIntent(intentMsg.intent, intentMsg.context);
      }
    },
    [onUserIntent],
  );
  const handleInitialized = useCallback(() => setReady(true), []);

  // Derive a reasonable default source attribution from the payload
  // shape — the merged emit_* record carries verdict/posting fields
  // only after later specialists have run, so the latest field wins.
  const derivedSource = useMemo(() => {
    if (source) return source;
    if (payload) {
      if (payload.action || payload.gl_code) return "poster";
      if (payload.verdict || payload.verdict_reason) return "validator";
      if (payload.vendor_name) return "extractor";
    }
    return "validator"; // audit-view default — KG sits under the validator
  }, [source, payload]);

  useEffect(() => {
    if (!ready || !frameRef.current || !update) return;
    frameRef.current.sendNotification("ui/update-data", {
      reset: true,
      source: derivedSource,
      live: true,
      ...update,
    });
  }, [ready, update, derivedSource]);

  if (!SANDBOX_URL) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-3 text-[10px] text-muted-foreground">
        Vendor KG widget unavailable — <code>NEXT_PUBLIC_MCP_SANDBOX_URL</code> is not configured.
      </div>
    );
  }

  return (
    <div
      className={
        height
          ? "flex flex-col overflow-hidden rounded-md border border-border bg-background"
          : "flex h-full min-h-[360px] flex-col overflow-hidden rounded-md border border-border bg-background"
      }
      style={height ? { height } : undefined}
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
          hostContext={{ theme: "light", displayMode: "inline" }}
          className="h-full w-full"
          title="Vendor Knowledge Graph"
        />
      </div>
    </div>
  );
}

/**
 * Defensive extraction across both supported input shapes:
 *
 * - Validator resultContent: free-form JSON with verdict/reasons/citations,
 *   and optionally an `invoice` passthrough from the orchestrator.
 * - Merged emit_* payload: flat object with vendor_name, invoice_number,
 *   po_reference, total, currency, audit_citations_csv, verdict, etc.
 *
 * The artefact pre-seeds with stylised defaults, so missing fields are
 * fine — they just keep their seed. Returns null only when no input at all.
 */
function buildUpdate(
  payload: Record<string, unknown> | null | undefined,
  resultJson: string | undefined,
): KgUpdate | null {
  let validator: Record<string, unknown> | null = null;
  if (resultJson) {
    try {
      validator = JSON.parse(resultJson) as Record<string, unknown>;
    } catch {
      validator = null;
    }
  }
  if (!payload && !validator) return null;

  const update: KgUpdate = {};

  // ── Citations ─────────────────────────────────────────────
  // Validator path: `citations` array of strings.
  if (validator && Array.isArray(validator.citations)) {
    update.citations = (validator.citations as unknown[]).map((c) => String(c)).slice(0, 8);
  }
  // Workbench path: `audit_citations_csv` comma-separated string from
  // the verdict payload. Each token is a citation reference (e.g.
  // "vendor_master:V-1042", "open_pos:PO-2026-0189").
  if (!update.citations && payload && typeof payload.audit_citations_csv === "string") {
    const csv = (payload.audit_citations_csv as string).trim();
    if (csv) {
      update.citations = csv
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean)
        .slice(0, 8);
    }
  }

  // ── Vendor record ──────────────────────────────────────────
  // Validator path: derive approved/status from the reasons array's
  // "vendor" check; pull name/id from the optional `invoice` passthrough.
  if (validator) {
    const reasons = Array.isArray(validator.reasons)
      ? (validator.reasons as Array<Record<string, unknown>>)
      : [];
    const vendorReason = reasons.find((r) =>
      String(r.check ?? "").toLowerCase().includes("vendor"),
    );
    if (vendorReason) {
      update.vendor = {
        approved: String(vendorReason.severity ?? "").toLowerCase() !== "fail",
        status: String(vendorReason.detail ?? "checked"),
      };
    }
    const invoice = validator.invoice as Record<string, unknown> | undefined;
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
  }
  // Workbench path: merged emit_* fields are flat on `payload`.
  if (payload) {
    const verdict = typeof payload.verdict === "string" ? (payload.verdict as string) : undefined;
    const approvedFromVerdict =
      verdict !== undefined ? !/fail|reject|block/i.test(verdict) : undefined;
    update.vendor = {
      ...update.vendor,
      name:
        update.vendor?.name ??
        (typeof payload.vendor_name === "string" ? (payload.vendor_name as string) : undefined),
      id:
        update.vendor?.id ??
        (typeof payload.vendor_id === "string" ? (payload.vendor_id as string) : undefined),
      approved: update.vendor?.approved ?? approvedFromVerdict,
      status: update.vendor?.status ?? verdict,
    };
    if (!update.po && typeof payload.po_reference === "string") {
      const total = typeof payload.total === "number" ? (payload.total as number) : undefined;
      const currency =
        typeof payload.currency === "string" ? (payload.currency as string) : undefined;
      update.po = { ref: payload.po_reference as string, total, currency };
    }
    if (!update.thisInvoice) {
      const total = typeof payload.total === "number" ? (payload.total as number) : undefined;
      const currency =
        typeof payload.currency === "string" ? (payload.currency as string) : undefined;
      update.thisInvoice = {
        number:
          typeof payload.invoice_number === "string"
            ? (payload.invoice_number as string)
            : undefined,
        amount: total,
        currency,
      };
    }
  }

  return update;
}
