import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { useSkillSessions } from "@/hooks/useSkillSessions";

function mockOk(sessions: object[], next_cursor: string | null = null) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({ sessions, next_cursor }),
  } as Response);
}

function mockError(status = 500) {
  mockFetch.mockResolvedValueOnce({ ok: false, status } as Response);
}

beforeEach(() => {
  mockFetch.mockReset();
  // Prevent unhandled rejection noise for abort
  mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ sessions: [], next_cursor: null }) } as Response);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("useSkillSessions", () => {
  it("fetches the correct endpoint for a given skillId", async () => {
    mockOk([]);

    renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/proxy/api/skills/my-skill/sessions",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("returns sessions on success", async () => {
    const session = {
      session_id: "sess-1",
      skill_id: "my-skill",
      owner_uid: "u1",
      title: "Test session",
      turn_count: 2,
      first_message_at: "2026-04-24T10:00:00Z",
      last_message_at: "2026-04-24T10:01:00Z",
      archived_at: null,
      document_ids: [],
      is_owner: true,
    };
    mockOk([session]);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].session_id).toBe("sess-1");
    expect(result.current.error).toBeNull();
  });

  it("returns empty list when no sessions", async () => {
    mockOk([]);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.sessions).toEqual([]);
  });

  it("sets error on HTTP failure", async () => {
    mockError(500);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe("Failed to load sessions");
  });

  it("does not fetch when skillId is null", () => {
    renderHook(() => useSkillSessions(null));
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("refetches when a sessions-changed event is dispatched (cross-panel sync)", async () => {
    mockOk([{ session_id: "s1" }]);
    mockOk([{ session_id: "s1" }, { session_id: "s2" }]);

    const { result } = renderHook(() => useSkillSessions("my-skill"));

    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Another panel deletes (or renames) a session and notifies.
    window.dispatchEvent(new CustomEvent("aitana:sessions-changed"));

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.sessions).toHaveLength(2));
  });
});
