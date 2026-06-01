"use client";

import { useDocument, type DocumentDetail } from "@/hooks/useDocument";
import type { ParseStatus } from "@/hooks/useDocBrowser";
import { DocumentHeader } from "./DocumentHeader";
import { DocumentFooter } from "./DocumentFooter";
import { DocumentViewer } from "./DocumentViewer";
import { PdfPreview } from "./PdfPreview";

interface DocumentPanelProps {
  docId: string;
}

// Genuine "still working on it" states. `pending_ai_extraction` is legacy:
// older docs are stuck in it because the AI extraction pipeline was never
// wired in this fork. New uploads use `preview_only` instead.
function isPendingStatus(status: ParseStatus): boolean {
  return status === "pending";
}

function isPdfFormat(sourceFormat: string): boolean {
  return sourceFormat.toLowerCase() === "pdf";
}

function pickCaption(doc: DocumentDetail | null): string {
  if (!doc) return "Loading document…";
  if (isPendingStatus(doc.parseStatus)) return "Parsing document…";
  return "Loading content…";
}

function Skeleton({ caption }: { caption: string }) {
  return (
    <div className="flex h-full flex-col" data-testid="doc-panel-loading">
      <div className="h-10 animate-pulse border-b bg-muted/40" />
      <div className="flex-1 space-y-3 p-3">
        <div className="text-xs text-muted-foreground">{caption}</div>
        {[80, 60, 90, 50].map((w) => (
          <div
            key={w}
            className="h-3 animate-pulse rounded bg-muted"
            style={{ width: `${w}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function TerminalMessage({
  doc,
  message,
}: {
  doc: DocumentDetail;
  message: string;
}) {
  return (
    <div className="flex h-full flex-col">
      <DocumentHeader doc={doc} />
      <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
        {message}
      </div>
    </div>
  );
}

export function DocumentPanel({ docId }: DocumentPanelProps) {
  const { doc, isLoading, error } = useDocument(docId);

  if (isLoading || (!doc && !error)) {
    return <Skeleton caption={pickCaption(doc)} />;
  }

  if (error || !doc) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {error ?? "Document preview unavailable."}
      </div>
    );
  }

  // For PDFs we can always show a native iframe preview, even on parse failure
  // or preview-only status. AILANG Parse can't structure PDFs anyway.
  const canPdfPreview = isPdfFormat(doc.sourceFormat) && !isPendingStatus(doc.parseStatus);
  if (canPdfPreview) {
    return (
      <div className="flex h-full flex-col overflow-hidden bg-muted/10">
        <DocumentHeader doc={doc} />
        <PdfPreview docId={doc.id} filename={doc.originalFilename} />
      </div>
    );
  }

  if (doc.parseStatus === "failed") {
    return (
      <TerminalMessage
        doc={doc}
        message={doc.parseError ?? "Document parse failed."}
      />
    );
  }

  if (isPendingStatus(doc.parseStatus)) {
    return <Skeleton caption="Parsing document…" />;
  }

  if (doc.parseStatus === "preview_only") {
    return (
      <TerminalMessage
        doc={doc}
        message="Preview unavailable for this format — the agent can still see the filename and metadata."
      />
    );
  }

  // Legacy: docs uploaded before the preview_only status existed are stuck in
  // pending_ai_extraction. Show a useful terminal message instead of looping.
  if (doc.parseStatus === "pending_ai_extraction") {
    return (
      <TerminalMessage
        doc={doc}
        message="Preview unavailable — try re-parsing this document from the sidebar."
      />
    );
  }

  if (!doc.blocks || doc.blocks.length === 0) {
    return (
      <TerminalMessage doc={doc} message="No preview content for this document." />
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-muted/10">
      <DocumentHeader doc={doc} />
      <DocumentViewer doc={doc} />
      {doc.summary && <DocumentFooter summary={doc.summary} />}
    </div>
  );
}
