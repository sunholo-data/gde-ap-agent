"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SkillMessage } from "@/hooks/useSkillAgent";
import { fetchWithAuth } from "@/lib/apiClient";

interface SessionMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

interface GetSessionMessagesResponse {
  messages: SessionMessage[];
  session_id: string;
}

interface UseSessionMessagesReturn {
  initialMessages: SkillMessage[];
  isLoadingHistory: boolean;
  historyError: string | null;
  sessionGone: boolean;
}

// Stranded-session-prevention (1.23) Option 1: distinguishes
// "session truly does not exist" (404) from transient errors (5xx,
// network). The chat page reads sessionGone and auto-redirects to a
// fresh URL via handleNewSession.
class SessionNotFoundError extends Error {
  constructor() {
    super("session not found");
    this.name = "SessionNotFoundError";
  }
}

let _msgCounter = 0;
function nextId(): string {
  return `hist-${++_msgCounter}`;
}

function toSkillMessage(m: SessionMessage): SkillMessage {
  return { id: nextId(), role: m.role, content: m.content };
}

export function useSessionMessages(sessionId: string | null): UseSessionMessagesReturn {
  const [initialMessages, setInitialMessages] = useState<SkillMessage[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [sessionGone, setSessionGone] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastSessionId = useRef<string | null>(null);

  const fetch_ = useCallback(
    (sid: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoadingHistory(true);
      setHistoryError(null);
      setSessionGone(false);

      fetchWithAuth(`/api/proxy/api/sessions/${encodeURIComponent(sid)}/messages`, {
        signal: controller.signal,
      })
        .then((res) => {
          if (res.status === 404) throw new SessionNotFoundError();
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json() as Promise<GetSessionMessagesResponse>;
        })
        .then((data) => {
          setInitialMessages(data.messages.map(toSkillMessage));
        })
        .catch((err: Error) => {
          if (err.name === "AbortError") return;
          if (err instanceof SessionNotFoundError) {
            setSessionGone(true);
            setInitialMessages([]);
            return;
          }
          setHistoryError("Couldn't load previous messages — starting fresh.");
          setInitialMessages([]);
        })
        .finally(() => {
          setIsLoadingHistory(false);
        });
    },
    [],
  );

  useEffect(() => {
    if (!sessionId) {
      setInitialMessages([]);
      setHistoryError(null);
      setSessionGone(false);
      return;
    }

    if (sessionId === lastSessionId.current) return;
    lastSessionId.current = sessionId;

    fetch_(sessionId);
    return () => abortRef.current?.abort();
  }, [sessionId, fetch_]);

  return { initialMessages, isLoadingHistory, historyError, sessionGone };
}
