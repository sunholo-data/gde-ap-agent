import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import DocumentHistoryPanel from "../DocumentHistoryPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSessions(overrides: Partial<typeof BASE_SESSION>[] = []) {
  return overrides.map((o, i) => ({ ...BASE_SESSION, session_id: `s${i}`, ...o }));
}

const BASE_SESSION = {
  session_id: "s0",
  document_ids: ["doc-1"],
  skill_id: "skill-1",
  owner_uid: "owner-uid",
  access_control: { type: "private" },
  title: "Revenue drivers Q1",
  turn_count: 5,
  first_message_at: new Date().toISOString(),
  last_message_at: new Date().toISOString(),
  archived_at: null,
  is_owner: true,
  can_fork: true,
};

function mockFetch(sessions: typeof BASE_SESSION[]) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ sessions, next_cursor: null }),
  });
}

const DEFAULT_PROPS = {
  documentId: "doc-1",
  activeSessionId: null,
  currentUserUid: "owner-uid",
  onSelectSession: vi.fn(),
  onNewSession: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DocumentHistoryPanel", () => {
  let originalFetch: typeof global.fetch;

  beforeEach(() => {
    originalFetch = global.fetch;
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders without errors when session list is empty", async () => {
    global.fetch = mockFetch([]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalledOnce());
    expect(screen.getByText("Conversations")).toBeInTheDocument();
    expect(screen.getByText("No conversations yet")).toBeInTheDocument();
  });

  it("renders Mine section with owner sessions", async () => {
    global.fetch = mockFetch(makeSessions([{ owner_uid: "owner-uid", is_owner: true }])) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => screen.getByText("Revenue drivers Q1"));
    expect(screen.getByText("Mine")).toBeInTheDocument();
  });

  it("renders Team section only when team sessions exist", async () => {
    const teamSess = { ...BASE_SESSION, session_id: "s1", owner_uid: "alice", is_owner: false };
    global.fetch = mockFetch([teamSess]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => screen.getByText("Team"));
    expect(screen.queryByText("Mine")).toBeInTheDocument();
  });

  it("hides Team section when no team sessions", async () => {
    global.fetch = mockFetch([]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalledOnce());
    expect(screen.queryByText("Team")).not.toBeInTheDocument();
  });

  it("calls onSelectSession when a session row is clicked", async () => {
    const onSelect = vi.fn();
    const sess = { ...BASE_SESSION, session_id: "s0", owner_uid: "owner-uid" };
    global.fetch = mockFetch([sess]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} onSelectSession={onSelect} />);

    await waitFor(() => screen.getByText("Revenue drivers Q1"));
    fireEvent.click(screen.getByText("Revenue drivers Q1"));

    expect(onSelect).toHaveBeenCalledWith("s0", "owner-uid");
  });

  it("highlights the active session", async () => {
    const sess = { ...BASE_SESSION, session_id: "s0" };
    global.fetch = mockFetch([sess]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} activeSessionId="s0" />);

    await waitFor(() => screen.getByText("Revenue drivers Q1"));
    // The row is a div wrapping the title button + rename button; the
    // active highlight lives on the wrapper.
    const row = screen.getByText("Revenue drivers Q1").closest("div.group")!;
    expect(row.className).toContain("bg-blue-50");
  });

  it("calls onNewSession when + New conversation is clicked", async () => {
    const onNew = vi.fn();
    global.fetch = mockFetch([]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} onNewSession={onNew} />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByText("+ New conversation"));

    expect(onNew).toHaveBeenCalledOnce();
  });

  it("collapses panel when header is clicked", async () => {
    global.fetch = mockFetch([]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalledOnce());

    // Click to collapse
    fireEvent.click(screen.getByText("Conversations"));
    expect(screen.queryByText("No conversations yet")).not.toBeInTheDocument();

    // Click to re-expand
    fireEvent.click(screen.getByText("Conversations"));
    await waitFor(() => expect(screen.getByText("No conversations yet")).toBeInTheDocument());
  });

  it("F2 (chat-history-fixes): rename refetches the session list on success", async () => {
    // Lock-in test for F2. The "rename doesn't refresh the list" report
    // turned out to be a false-positive in the original diagnostic — the
    // DocumentHistoryPanel parent already calls refetch() after a
    // successful PATCH (see handleRename). This test ensures that
    // behaviour cannot silently regress: any future refactor that drops
    // the refetch call will fail here.
    const sess = { ...BASE_SESSION, session_id: "s0", owner_uid: "owner-uid", title: "Old title" };

    // First call: GET /api/documents/{id}/sessions returns the original list.
    // Second call: PATCH /api/sessions/{id} returns 200.
    // Third call: GET /api/documents/{id}/sessions (the refetch) returns the
    //             same list — it's the *fact* that fetch was called a third
    //             time that we assert, not a different payload.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [sess], next_cursor: null }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [{ ...sess, title: "New title" }], next_cursor: null }),
      });
    global.fetch = fetchMock as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => screen.getByText("Old title"));

    // Click the rename pencil — selector matches the aria-label set on
    // the rename button in DocumentHistoryPanel.
    fireEvent.click(screen.getByRole("button", { name: /rename old title/i }));
    const input = await screen.findByLabelText("Rename conversation");
    fireEvent.change(input, { target: { value: "New title" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // The PATCH must fire, then the parent must re-issue the GET. Three
    // total fetches: initial GET, PATCH, refetch GET.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    const patchCall = fetchMock.mock.calls[1];
    expect(patchCall[0]).toContain("/api/proxy/api/sessions/s0");
    expect(patchCall[1]?.method).toBe("PATCH");

    const refetchCall = fetchMock.mock.calls[2];
    expect(refetchCall[0]).toContain("/api/proxy/api/documents/doc-1/sessions");
  });

  // ---------------------------------------------------------------------------
  // session-delete-ui (1.17)
  // ---------------------------------------------------------------------------

  it("1.17: trash icon is visible on owner's own session rows but NOT on team rows", async () => {
    const ownSess = { ...BASE_SESSION, session_id: "s-own", owner_uid: "owner-uid", title: "Mine" };
    const teamSess = { ...BASE_SESSION, session_id: "s-team", owner_uid: "alice", title: "Theirs" };
    global.fetch = mockFetch([ownSess, teamSess]) as typeof global.fetch;

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);

    await waitFor(() => screen.getByText("Mine"));
    await waitFor(() => screen.getByText("Theirs"));

    // Owner row: trash button exists and matches the aria-label pattern.
    expect(
      screen.getByRole("button", { name: /delete mine/i }),
    ).toBeInTheDocument();
    // Team row: NO trash button. The rename pencil is also absent for non-owners,
    // but specifically we assert the delete affordance is gated on ownership.
    expect(
      screen.queryByRole("button", { name: /delete theirs/i }),
    ).toBeNull();
  });

  it("1.17: clicking trash + confirming calls DELETE and refetches", async () => {
    const sess = { ...BASE_SESSION, session_id: "s-del", owner_uid: "owner-uid", title: "Goodbye" };
    const fetchMock = vi
      .fn()
      // 1. initial GET (panel mount)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [sess], next_cursor: null }),
      })
      // 2. DELETE
      .mockResolvedValueOnce({ ok: true, status: 204, json: () => Promise.resolve({}) })
      // 3. refetch GET
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [], next_cursor: null }),
      });
    global.fetch = fetchMock as typeof global.fetch;

    // Auto-confirm the window.confirm() dialog.
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);
    await waitFor(() => screen.getByText("Goodbye"));

    fireEvent.click(screen.getByRole("button", { name: /delete goodbye/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));

    expect(confirmSpy).toHaveBeenCalled();

    const deleteCall = fetchMock.mock.calls[1];
    expect(deleteCall[0]).toContain("/api/proxy/api/sessions/s-del");
    expect(deleteCall[1]?.method).toBe("DELETE");

    const refetchCall = fetchMock.mock.calls[2];
    expect(refetchCall[0]).toContain("/api/proxy/api/documents/doc-1/sessions");

    confirmSpy.mockRestore();
  });

  it("1.17: deleting the active session invokes onDeleteActive so the URL can clear", async () => {
    const sess = { ...BASE_SESSION, session_id: "s-active", owner_uid: "owner-uid", title: "Active one" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [sess], next_cursor: null }),
      })
      .mockResolvedValueOnce({ ok: true, status: 204, json: () => Promise.resolve({}) })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: [], next_cursor: null }),
      });
    global.fetch = fetchMock as typeof global.fetch;
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    const onDeleteActive = vi.fn();

    render(
      <DocumentHistoryPanel
        {...DEFAULT_PROPS}
        activeSessionId="s-active"
        onDeleteActive={onDeleteActive}
      />,
    );

    await waitFor(() => screen.getByText("Active one"));
    fireEvent.click(screen.getByRole("button", { name: /delete active one/i }));

    await waitFor(() => expect(onDeleteActive).toHaveBeenCalledTimes(1));

    confirmSpy.mockRestore();
  });

  it("1.17: cancelling the confirm dialog does NOT call DELETE", async () => {
    const sess = { ...BASE_SESSION, session_id: "s-keep", owner_uid: "owner-uid", title: "Keep me" };
    global.fetch = mockFetch([sess]) as typeof global.fetch;
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<DocumentHistoryPanel {...DEFAULT_PROPS} />);
    await waitFor(() => screen.getByText("Keep me"));

    fireEvent.click(screen.getByRole("button", { name: /delete keep me/i }));

    // Only the initial GET — no DELETE.
    await new Promise((r) => setTimeout(r, 30)); // give any async work a tick
    expect(global.fetch).toHaveBeenCalledTimes(1);

    confirmSpy.mockRestore();
  });
});
