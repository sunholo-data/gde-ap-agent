"use client";

import { useState } from "react";
import { useDocBrowser } from "@/hooks/useDocBrowser";

interface DocparsePickerProps {
  uid: string;
  disabled?: boolean;
  onSubmit: (input: { document_id: string }) => void;
}

/**
 * Hand-rolled form for the docparse "Run Standalone" affordance. No chat
 * box — the only structured input is a Firestore parsed_documents ID.
 * The user can paste an ID directly or pick from their docs list.
 */
export function DocparsePicker({ uid, disabled, onSubmit }: DocparsePickerProps) {
  const browser = useDocBrowser(uid);
  const [docId, setDocId] = useState("");

  const valid = docId.trim().length > 0;

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !disabled) onSubmit({ document_id: docId.trim() });
      }}
    >
      <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/70">
        Document ID
      </label>
      <input
        type="text"
        value={docId}
        onChange={(e) => setDocId(e.target.value)}
        placeholder="Paste a parsed_documents ID, or pick below"
        disabled={disabled}
        className="w-full rounded border border-border bg-background px-2 py-1.5 font-mono text-[11px] text-foreground placeholder:text-muted-foreground/40 focus:border-primary/40 focus:outline-none"
      />

      {browser.documents.length > 0 && (
        <div className="space-y-1">
          <label className="block text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/70">
            Or pick a recent document
          </label>
          <div className="max-h-32 overflow-y-auto rounded border border-border bg-background">
            {browser.documents.slice(0, 20).map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => setDocId(d.id)}
                disabled={disabled}
                className="block w-full truncate px-2 py-1 text-left text-[11px] hover:bg-primary/10 hover:text-primary"
                title={`${d.originalFilename} — ${d.id}`}
              >
                <span className="font-mono text-[9px] text-muted-foreground/60">{d.id.slice(0, 8)}</span>{" "}
                {d.originalFilename}
              </button>
            ))}
          </div>
        </div>
      )}

      <button
        type="submit"
        disabled={!valid || disabled}
        className="rounded-lg bg-primary px-3 py-1.5 text-[11px] font-bold text-primary-foreground transition-all hover:shadow-[0_0_8px_rgba(232,168,0,0.3)] disabled:opacity-40 disabled:shadow-none"
      >
        Run DocParse
      </button>
    </form>
  );
}
