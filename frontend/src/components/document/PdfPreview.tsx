"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";

interface PdfPreviewProps {
  docId: string;
  filename: string;
}

interface PreviewUrlResponse {
  url: string;
  expiresInSeconds?: number;
}

export function PdfPreview({ docId, filename }: PdfPreviewProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setUrl(null);
    setError(null);

    (async () => {
      try {
        const res = await fetchWithAuth(`/api/proxy/api/documents/${docId}/preview-url`);
        if (cancelled) return;
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setError((body as { detail?: string }).detail ?? `Preview unavailable (${res.status})`);
          return;
        }
        const data = (await res.json()) as PreviewUrlResponse;
        setUrl(data.url);
      } catch {
        if (!cancelled) setError("Network error — could not load preview");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [docId]);

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-sm text-muted-foreground">
        {error}
      </div>
    );
  }

  if (!url) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-xs text-muted-foreground">
        Loading preview…
      </div>
    );
  }

  return (
    <iframe
      src={url}
      title={filename}
      className="flex-1 w-full h-full border-0"
      data-testid="pdf-preview-iframe"
    />
  );
}
