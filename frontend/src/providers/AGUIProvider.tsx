// Workshop W5c — AG-UI: The Frontend Provider
// We use @ag-ui/client directly instead of wrapping in <CopilotKit>. CopilotKit's
// `runtimeUrl` expects a GraphQL CopilotKit-Runtime endpoint, not a bare AG-UI SSE
// stream. Going AG-UI-native keeps the stack one layer thinner and avoids silent
// failures where 200 OK masked every message being dropped at the GraphQL layer.
// See memory: gotcha_copilotkit_not_agui_native.md for the full incident.

"use client";

import { HttpAgent } from "@ag-ui/client";
import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useAuth } from "@/contexts/AuthContext";

/**
 * AG-UI-native provider. Exposes one `HttpAgent` per `skillId`, targeting the
 * backend's SSE endpoint via the Next `/api/proxy` forwarder. The provider
 * rebuilds the agent when the refreshed Firebase ID token changes, so the
 * next `runAgent()` carries a fresh `Authorization: Bearer …` header that the
 * backend's `Depends(get_current_user)` can verify.
 *
 * We intentionally skip CopilotKit's `<CopilotKit>` provider here: its
 * `runtimeUrl` is a CopilotKit-Runtime GraphQL endpoint, not a bare AG-UI
 * SSE one. Going AG-UI-native with `@ag-ui/client` keeps the protocol stack
 * one layer thinner and matches the design doc's "thin client, fat protocol"
 * framing. If we later adopt `<CopilotChat>` for off-the-shelf UI polish,
 * we'll wrap it here alongside — not in place of — this context.
 */
const AGUIAgentContext = createContext<HttpAgent | null>(null);

export function AGUIProvider({
  skillId,
  sessionId,
  children,
}: {
  skillId: string;
  /** Resume an existing chat by seeding the HttpAgent's threadId. When
   * absent, the agent generates a fresh UUID — that becomes the new
   * session id, which the page should then write to the URL. */
  sessionId?: string;
  children: ReactNode;
}) {
  const { getIdToken } = useAuth();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getIdToken().then((t) => {
      if (!cancelled) setToken(t);
    });
    return () => {
      cancelled = true;
    };
  }, [getIdToken]);

  const agent = useMemo(() => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    return new HttpAgent({
      url: `/api/proxy/api/skill/${encodeURIComponent(skillId)}/stream`,
      headers,
      threadId: sessionId,
    });
  }, [skillId, token, sessionId]);

  return (
    <AGUIAgentContext.Provider value={agent}>
      {children}
    </AGUIAgentContext.Provider>
  );
}

export function useAGUIAgent(): HttpAgent {
  const agent = useContext(AGUIAgentContext);
  if (!agent) {
    throw new Error("useAGUIAgent must be used within an AGUIProvider");
  }
  return agent;
}
