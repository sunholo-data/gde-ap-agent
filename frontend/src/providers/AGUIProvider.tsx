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
  useRef,
  useState,
} from "react";
import { useAuth } from "@/contexts/AuthContext";
import { subscribeToIdToken } from "@/lib/firebase";

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
  const [initialToken, setInitialToken] = useState<string | null>(null);
  const [initialTokenLoaded, setInitialTokenLoaded] = useState(false);

  // One-shot initial token fetch — populates the constructor's headers
  // so the first request fires with a Bearer. After this, the
  // onIdTokenChanged subscription below mutates the same headers
  // object in-place; never rebuilds the agent.
  useEffect(() => {
    let cancelled = false;
    void getIdToken().then((t) => {
      if (cancelled) return;
      setInitialToken(t);
      setInitialTokenLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [getIdToken]);

  // Headers Record is created ONCE and threaded into the HttpAgent's
  // `headers` property. We mutate this object on every Firebase
  // token-refresh (auto-fires ~5min before the 1h expiry) so the next
  // request sends the new Bearer without rebuilding the agent — which
  // would destroy `agent.messages` mid-conversation. HttpAgent reads
  // `this.headers` per-request, so in-place mutation is sufficient.
  const headersRef = useRef<Record<string, string>>({});

  const agent = useMemo(() => {
    if (initialToken) headersRef.current.Authorization = `Bearer ${initialToken}`;
    return new HttpAgent({
      url: `/api/proxy/api/skill/${encodeURIComponent(skillId)}/stream`,
      headers: headersRef.current,
      threadId: sessionId,
    });
    // initialTokenLoaded gates the first agent build so the constructor
    // sees a token. After build, the agent is stable; the headers ref
    // is mutated on subsequent token refreshes via the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillId, sessionId, initialTokenLoaded]);

  // Long-running session keep-alive: mutate agent.headers in place on
  // every token refresh. Without this, Firebase tokens expire ~1h after
  // sign-in and every subsequent /api/skill/{id}/stream request returns
  // 401, looking to the user like "the agent is broken" mid-demo.
  useEffect(() => {
    return subscribeToIdToken((token) => {
      if (token) {
        agent.headers.Authorization = `Bearer ${token}`;
        headersRef.current.Authorization = `Bearer ${token}`;
      } else {
        delete agent.headers.Authorization;
        delete headersRef.current.Authorization;
      }
    });
  }, [agent]);

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
