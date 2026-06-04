"use client";

import { useState } from "react";
import { getIdToken } from "@/lib/firebase";
import { SAMPLE_INVOICES, type SampleInvoice } from "@/lib/sampleInvoices";

/**
 * Empty-state component for the ap-orchestrator chat page. Three curated
 * fixture invoices in different formats. Clicking one fetches the static
 * file from /demo-invoices/, uploads it via the standard documents API,
 * then calls onSampleSelected so the chat page can mark it
 * included-in-context and (if auto-process is enabled) fire the first
 * pipeline turn.
 *
 * Lives in /public/demo-invoices/ — see lib/sampleInvoices.ts for the
 * curated set.
 */

interface SampleInvoicePickerProps {
  skillId: string;
  onSampleSelected: (docId: string, filename: string) => void | Promise<void>;
}

type Status = "idle" | "loading" | "error";

export function SampleInvoicePicker({ skillId, onSampleSelected }: SampleInvoicePickerProps) {
  const [busyFilename, setBusyFilename] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handlePick(sample: SampleInvoice) {
    if (busyFilename) return;
    setBusyFilename(sample.filename);
    setStatus("loading");
    setErrorMsg(null);
    try {
      // Fetch the static fixture, build a File, post to the same upload
      // endpoint the drag-drop zone uses.
      const fileRes = await fetch(`/demo-invoices/${sample.filename}`);
      if (!fileRes.ok) throw new Error(`Could not load ${sample.filename} (${fileRes.status})`);
      const blob = await fileRes.blob();
      const file = new File([blob], sample.filename, { type: sample.mime });

      const token = await getIdToken();
      const formData = new FormData();
      formData.append("file", file);
      if (skillId) formData.append("skill_id", skillId);

      const uploadRes = await fetch("/api/proxy/api/documents/upload", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!uploadRes.ok) throw new Error(`Upload failed (${uploadRes.status})`);
      const data = (await uploadRes.json()) as { docId?: string };
      if (!data.docId) throw new Error("Upload succeeded but no docId returned");

      await onSampleSelected(data.docId, sample.filename);
      // Leave busy state alone — the parent will likely unmount this picker
      // as soon as it pushes the first chat message.
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setBusyFilename(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8">
      <div className="mb-6 text-center">
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          Start the demo
        </p>
        <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground">
          Pick a sample invoice
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          One click runs the full four-agent pipeline. Or drop your own file in the sidebar.
        </p>
      </div>

      <ul className="space-y-2">
        {SAMPLE_INVOICES.map((sample) => {
          const isBusy = busyFilename === sample.filename;
          return (
            <li key={sample.filename}>
              <button
                type="button"
                onClick={() => void handlePick(sample)}
                disabled={busyFilename !== null}
                className="group flex w-full items-center gap-4 rounded-md border border-border bg-background p-4 text-left transition-all hover:border-primary/50 hover:bg-muted/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-border bg-muted/30 font-mono text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                  {sample.country}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-display text-sm font-semibold text-foreground">
                      {sample.vendor}
                    </span>
                    <span className="font-mono text-xs tabular-nums text-foreground">
                      {sample.amount}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {sample.caption}
                  </p>
                </div>
                <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-primary opacity-0 transition-opacity group-hover:opacity-100">
                  {isBusy ? "Uploading…" : "Try this →"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {status === "error" && errorMsg && (
        <p className="mt-3 text-center text-xs text-destructive">{errorMsg}</p>
      )}

      <p className="mt-6 text-center font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        Or drop a file in the sidebar →
      </p>
    </div>
  );
}
