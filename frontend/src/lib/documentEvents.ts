"use client";

/**
 * Tiny pub/sub for "a document was just imported" events.
 *
 * Parallel to ``sessionEvents.ts``. GCSFileItem fires this on a
 * successful import so DocListView can visually connect the cause
 * (clicked Import on a remote file) to the effect (new doc in My
 * Documents under a source-named folder).
 *
 * Listeners typically open the right folder, scroll the new doc into
 * view, and flash it briefly — the auto-highlight piece of the
 * sidebar-Option-2 behaviour.
 *
 * SSR-safe: dispatch / subscribe bail early under server render.
 */

const DOCUMENT_IMPORTED_EVENT = "aitana:document-imported";

export interface DocumentImportedDetail {
  /** Firestore parsed_documents id assigned to the new doc. */
  docId: string;
  /** Display name of the folder it landed in (eg. "Example Invoices",
   * "gs://my-bucket", "Local uploads"). Used to open the right
   * accordion section. */
  folderName?: string;
  /** Original filename. Surface in toasts / aria-live announcements. */
  filename?: string;
}

export function notifyDocumentImported(detail: DocumentImportedDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<DocumentImportedDetail>(DOCUMENT_IMPORTED_EVENT, { detail }),
  );
}

export function subscribeDocumentImported(
  handler: (detail: DocumentImportedDetail) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const wrapped = (e: Event) => {
    const detail = (e as CustomEvent<DocumentImportedDetail>).detail;
    if (detail) handler(detail);
  };
  window.addEventListener(DOCUMENT_IMPORTED_EVENT, wrapped);
  return () => window.removeEventListener(DOCUMENT_IMPORTED_EVENT, wrapped);
}
