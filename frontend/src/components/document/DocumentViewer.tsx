import { BlocksRenderer } from "./BlocksRenderer";
import type { DocumentDetail } from "@/hooks/useDocument";

interface DocumentViewerProps {
  doc: DocumentDetail;
}

export function DocumentViewer({ doc }: DocumentViewerProps) {
  if (!doc.blocks || doc.blocks.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
        Document preview unavailable.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <BlocksRenderer blocks={doc.blocks} />
    </div>
  );
}
