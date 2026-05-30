"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";
import { subscribeSessionsChanged } from "@/lib/sessionEvents";

export interface ChatSessionSummary {
  session_id: string;
  document_ids: string[];
  skill_id: string;
  owner_uid: string;
  title: string | null;
  turn_count: number;
  first_message_at: string;
  last_message_at: string;
  archived_at: string | null;
  is_owner: boolean;
}

interface ListSessionsResponse {
  sessions: ChatSessionSummary[];
  next_cursor: string | null;
}

interface UseSkillSessionsReturn {
  sessions: ChatSessionSummary[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSkillSessions(skillId: string | null): UseSkillSessionsReturn {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetch_ = useCallback(() => {
    if (!skillId) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    fetchWithAuth(`/api/proxy/api/skills/${encodeURIComponent(skillId)}/sessions`, {
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<ListSessionsResponse>;
      })
      .then((data) => {
        setSessions(data.sessions);
      })
      .catch((err: Error) => {
        if (err.name !== "AbortError") {
          setError("Failed to load sessions");
        }
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [skillId]);

  useEffect(() => {
    fetch_();
    return () => abortRef.current?.abort();
  }, [fetch_]);

  useEffect(() => {
    const onFocus = () => fetch_();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [fetch_]);

  // Cross-panel sync: when ANY session list (skill-level or per-document)
  // mutates, both hooks refetch. See lib/sessionEvents.ts.
  useEffect(() => subscribeSessionsChanged(fetch_), [fetch_]);

  return { sessions, isLoading, error, refetch: fetch_ };
}
