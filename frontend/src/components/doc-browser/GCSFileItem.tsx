"use client";

import { useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";
import type { GCSObject } from "@/hooks/useGCSBucket";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fileIcon(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const icons: Record<string, string> = {
    docx: "📄",
    xlsx: "📊",
    csv: "📋",
    eml: "✉️",
    odt: "📃",
    mbox: "📬",
    pdf: "📑",
    pptx: "📑",
  };
  return icons[ext] ?? "📄";
}

type ImportState = "idle" | "importing" | "done" | "error";

interface GCSFileItemProps {
  obj: GCSObject;
  bucket: string;
  skillId?: string;
}

export function GCSFileItem({ obj, bucket, skillId = "" }: GCSFileItemProps) {
  const [state, setState] = useState<ImportState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleImport() {
    setState("importing");
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth("/api/proxy/api/gcs/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bucket, path: obj.name, skill_id: skillId }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `Error ${res.status}`);
      }
      setState("done");
    } catch (err) {
      setState("error");
      setErrorMsg(err instanceof Error ? err.message : "Import failed");
    }
  }

  return (
    <div className="group flex items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent">
      <span aria-hidden="true">{fileIcon(obj.displayName)}</span>
      <span className="min-w-0 flex-1 truncate text-foreground">{obj.displayName}</span>
      <span className="shrink-0 text-[10px] text-muted-foreground">{formatBytes(obj.size)}</span>
      {state === "idle" && (
        <button
          type="button"
          onClick={() => void handleImport()}
          className="shrink-0 rounded border border-primary/30 px-1.5 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/10"
        >
          Import
        </button>
      )}
      {state === "importing" && (
        <span className="shrink-0 animate-pulse text-[10px] text-muted-foreground">
          Importing…
        </span>
      )}
      {state === "done" && (
        <span className="shrink-0 text-[10px] text-emerald-500">Done</span>
      )}
      {state === "error" && (
        <button
          type="button"
          onClick={() => setState("idle")}
          title={errorMsg ?? "Import failed"}
          className="shrink-0 text-[10px] text-destructive hover:underline"
        >
          Error
        </button>
      )}
    </div>
  );
}
