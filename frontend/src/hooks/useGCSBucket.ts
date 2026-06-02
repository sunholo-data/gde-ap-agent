"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";

export interface GCSObject {
  name: string;
  displayName: string;
  size: number;
  contentType: string;
  updated: string;
}

interface GCSBucketState {
  objects: GCSObject[];
  prefixes: string[];
  isLoading: boolean;
  error: string | null;
  saEmail: string | null;
  refetch: () => void;
}

export function useGCSBucket(bucket: string, prefix = ""): GCSBucketState {
  const [objects, setObjects] = useState<GCSObject[]>([]);
  const [prefixes, setPrefixes] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saEmail, setSaEmail] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doFetch = useCallback(async () => {
    if (!bucket) {
      setObjects([]);
      setPrefixes([]);
      setError(null);
      setSaEmail(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    setSaEmail(null);
    try {
      const params = new URLSearchParams({ bucket, prefix, delimiter: "/" });
      const res = await fetchWithAuth(`/api/proxy/api/gcs/list?${params.toString()}`);
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail ?? `Error ${res.status}`);
        setObjects([]);
        return;
      }
      const data = (await res.json()) as {
        objects: GCSObject[];
        prefixes: string[];
        error?: string | null;
        sa_email?: string | null;
      };
      setObjects(data.objects ?? []);
      setPrefixes(data.prefixes ?? []);
      if (data.error) {
        setError(data.error);
        setSaEmail(data.sa_email ?? null);
      }
    } catch {
      setError("Network error — check connection");
    } finally {
      setIsLoading(false);
    }
  }, [bucket, prefix]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void doFetch();
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [doFetch]);

  return { objects, prefixes, isLoading, error, saEmail, refetch: doFetch };
}
