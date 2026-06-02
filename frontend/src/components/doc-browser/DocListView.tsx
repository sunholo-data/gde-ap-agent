"use client";

import { useEffect, useRef, useState } from "react";
import type { ParsedDocument } from "@/hooks/useDocBrowser";
import { useDocBrowser } from "@/hooks/useDocBrowser";
import { DocListFolder } from "./DocListFolder";
import { DocListSearch } from "./DocListSearch";
import { DocParseProgress } from "./DocParseProgress";
import { subscribeDocumentImported } from "@/lib/documentEvents";

interface DocListViewProps {
  uid: string;
  onDocClick?: (doc: ParsedDocument) => void;
}

/** How long the freshly-imported doc keeps its primary glow (ms). */
const HIGHLIGHT_DURATION_MS = 3500;

export function DocListView({ uid, onDocClick }: DocListViewProps) {
  const {
    folders,
    activeFolderId,
    documents,
    searchQuery,
    filteredDocuments,
    setActiveFolderId,
    setSearchQuery,
  } = useDocBrowser(uid);

  // Stats for active folder
  const activeFolder = folders.find((f) => f.id === activeFolderId) ?? null;
  const parsedCount = documents.filter((d) => d.parseStatus === "parsed").length;
  const failedCount = documents.filter((d) => d.parseStatus === "failed").length;
  const docCount = documents.length;

  function handleDocClick(doc: ParsedDocument) {
    onDocClick?.(doc);
  }

  // Auto-highlight after a GCS import (sidebar-Option-2):
  // 1. open the source-named folder ("Example Invoices" / "gs://…")
  // 2. flash the new doc in the list so the import → my-docs link is visible
  // The pending docId may arrive before the Firestore listener has flushed
  // the new row, so we keep the highlight until both timers + the doc's
  // appearance in the documents array converge.
  const [highlightedDocId, setHighlightedDocId] = useState<string | null>(null);
  const pendingDocIdRef = useRef<string | null>(null);
  const pendingFolderNameRef = useRef<string | null>(null);

  useEffect(() => {
    return subscribeDocumentImported(({ docId, folderName }) => {
      pendingDocIdRef.current = docId;
      pendingFolderNameRef.current = folderName ?? null;
      setHighlightedDocId(docId);
      // Auto-clear so the glow doesn't persist forever.
      const t = window.setTimeout(() => {
        setHighlightedDocId((cur) => (cur === docId ? null : cur));
        pendingDocIdRef.current = null;
        pendingFolderNameRef.current = null;
      }, HIGHLIGHT_DURATION_MS);
      return () => window.clearTimeout(t);
    });
  }, []);

  // Open the source-named folder once it appears in the folders list
  // (the Firestore listener may take a tick to flush a brand-new folder).
  useEffect(() => {
    const wantedName = pendingFolderNameRef.current;
    if (!wantedName) return;
    const match = folders.find((f) => f.name === wantedName);
    if (match && match.id !== activeFolderId) {
      setActiveFolderId(match.id);
    }
  }, [folders, activeFolderId, setActiveFolderId]);

  // Scroll the highlighted doc into view once it appears in the list.
  const docRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());
  useEffect(() => {
    if (!highlightedDocId) return;
    const node = docRefs.current.get(highlightedDocId);
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [highlightedDocId, filteredDocuments]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold text-foreground">My Documents</span>
        {folders.length > 0 && (
          <span className="text-[10px] text-muted-foreground">
            {folders.length} folder{folders.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <DocListSearch value={searchQuery} onChange={setSearchQuery} />

      <div className="min-h-0 flex-1 overflow-y-auto px-1 py-1">
        {folders.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">
            No documents yet.
            <br />
            Upload a file to get started.
          </p>
        )}

        {searchQuery.trim() !== "" ? (
          // Flat search results across all docs in the active folder
          <div className="space-y-0.5 px-1">
            {filteredDocuments.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                No results for &ldquo;{searchQuery}&rdquo;
              </p>
            ) : (
              filteredDocuments.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => handleDocClick(doc)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent"
                >
                  <span className="min-w-0 flex-1 truncate">{doc.originalFilename}</span>
                </button>
              ))
            )}
          </div>
        ) : (
          // Folder accordion view
          <div className="space-y-0.5 px-1">
            {folders.map((folder) => (
              <DocListFolder
                key={folder.id}
                folder={folder}
                documents={folder.id === activeFolderId ? filteredDocuments : []}
                isActive={folder.id === activeFolderId}
                onSelect={setActiveFolderId}
                onDocClick={handleDocClick}
                highlightedDocId={highlightedDocId}
                onItemMount={(id, node) => {
                  if (node) docRefs.current.set(id, node);
                  else docRefs.current.delete(id);
                }}
              />
            ))}
          </div>
        )}
      </div>

      {activeFolder && (
        <DocParseProgress parsedCount={parsedCount} failedCount={failedCount} docCount={docCount} />
      )}
    </div>
  );
}
