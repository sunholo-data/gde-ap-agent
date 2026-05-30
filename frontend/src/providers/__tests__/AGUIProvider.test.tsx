import { render, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/contexts/AuthContext";
import { AGUIProvider, useAGUIAgent } from "@/providers/AGUIProvider";

vi.mock("@/lib/firebase", () => ({
  subscribeToAuthState: (cb: (u: null) => void) => {
    queueMicrotask(() => cb(null));
    return () => {};
  },
  getIdToken: async () => "test-token",
  signInWithGoogle: async () => {},
  signInWithGoogleRedirect: async () => {},
  signOut: async () => {},
}));

// Spy on HttpAgent construction without replacing the class — consumers still
// get a real AbstractAgent subclass, which matters for useAGUIAgent().
const httpAgentCtor = vi.fn();
vi.mock("@ag-ui/client", async () => {
  const actual = await vi.importActual<typeof import("@ag-ui/client")>(
    "@ag-ui/client",
  );
  class SpiedHttpAgent extends actual.HttpAgent {
    constructor(cfg: ConstructorParameters<typeof actual.HttpAgent>[0]) {
      super(cfg);
      httpAgentCtor(cfg);
    }
  }
  return { ...actual, HttpAgent: SpiedHttpAgent };
});

describe("AGUIProvider", () => {
  it("renders children and builds an HttpAgent targeting the skill stream endpoint", async () => {
    const { getByText } = render(
      <AuthProvider>
        <AGUIProvider skillId="my-skill">
          <div>chat-content</div>
        </AGUIProvider>
      </AuthProvider>,
    );

    expect(getByText("chat-content")).toBeTruthy();

    await waitFor(() => {
      const withAuth = httpAgentCtor.mock.calls.find(
        ([cfg]) => cfg?.headers?.Authorization === "Bearer test-token",
      );
      expect(withAuth).toBeDefined();
    });

    const lastCfg = httpAgentCtor.mock.calls.at(-1)?.[0];
    expect(lastCfg?.url).toBe("/api/proxy/api/skill/my-skill/stream");
  });

  it("URL-encodes skillId so slashes/spaces don't break the endpoint", async () => {
    render(
      <AuthProvider>
        <AGUIProvider skillId="weird id/with slash">
          <div />
        </AGUIProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      const lastCfg = httpAgentCtor.mock.calls.at(-1)?.[0];
      expect(lastCfg?.url).toBe(
        "/api/proxy/api/skill/weird%20id%2Fwith%20slash/stream",
      );
    });
  });

  it("useAGUIAgent throws outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAGUIAgent())).toThrow(
      /must be used within an AGUIProvider/,
    );
    spy.mockRestore();
  });

  it("D1 (chat-history-deep-fixes H1): rebuilds the HttpAgent when sessionId changes from undefined to a server-assigned value", async () => {
    // The real-world failure: a fresh chat starts with sessionId=undefined.
    // After the first turn the chat page's URL-writeback effect rewrites
    // ?session=<id>, which propagates to <AGUIProvider sessionId={id}>.
    // useMemo([skillId, token, sessionId]) sees the dep change and builds
    // a NEW HttpAgent instance — the old one (with [Q1, A1] in messages)
    // is discarded. This test asserts the rebuild *does* happen so we
    // know what mechanism the fix needs to neutralise (pre-allocate
    // threadId at mount so it never changes from undefined to a value).
    httpAgentCtor.mockClear();

    const { rerender } = render(
      <AuthProvider>
        <AGUIProvider skillId="skill-x" sessionId={undefined}>
          <div />
        </AGUIProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      // Initial constructor call(s) — there can be 1 (no token yet) + 1
      // (with token) depending on auth bootstrap timing. Snapshot that count.
      expect(httpAgentCtor.mock.calls.length).toBeGreaterThanOrEqual(1);
    });
    const callsBeforeWriteback = httpAgentCtor.mock.calls.length;

    // Simulate the URL-writeback: sessionId changes from undefined to <id>.
    rerender(
      <AuthProvider>
        <AGUIProvider skillId="skill-x" sessionId="server-assigned-id-123">
          <div />
        </AGUIProvider>
      </AuthProvider>,
    );

    // Pre-fix: a NEW HttpAgent is constructed because useMemo's deps
    // include sessionId. Post-fix (option a from the design doc): the
    // threadId is pre-allocated at chat-page mount, so AGUIProvider never
    // sees this transition — the constructor count stays equal.
    await waitFor(() => {
      expect(httpAgentCtor.mock.calls.length).toBeGreaterThan(callsBeforeWriteback);
    });

    // Confirm the new instance got the new threadId
    const newestCfg = httpAgentCtor.mock.calls.at(-1)?.[0];
    expect(newestCfg?.threadId).toBe("server-assigned-id-123");
  });
});
