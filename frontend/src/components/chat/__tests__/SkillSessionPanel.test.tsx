import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SkillSessionPanel } from "../SkillSessionPanel";
import type { ChatSessionSummary } from "@/hooks/useSkillSessions";

function makeSession(overrides: Partial<ChatSessionSummary> = {}): ChatSessionSummary {
  return {
    session_id: "sess-1",
    skill_id: "skill-x",
    owner_uid: "u1",
    title: "Test session",
    turn_count: 2,
    first_message_at: new Date(Date.now() - 3_600_000).toISOString(),
    last_message_at: new Date(Date.now() - 60_000).toISOString(),
    archived_at: null,
    document_ids: [],
    is_owner: true,
    ...overrides,
  };
}

describe("SkillSessionPanel", () => {
  it("renders session titles", () => {
    const sessions = [
      makeSession({ session_id: "sess-1", title: "First session" }),
      makeSession({ session_id: "sess-2", title: "Second session" }),
    ];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={vi.fn()}
      />,
    );
    expect(screen.getByText("First session")).toBeInTheDocument();
    expect(screen.getByText("Second session")).toBeInTheDocument();
  });

  it("marks the active session with aria-current", () => {
    const sessions = [
      makeSession({ session_id: "sess-1", title: "Active" }),
      makeSession({ session_id: "sess-2", title: "Inactive" }),
    ];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId="sess-1"
        isLoading={false}
        onSelectSession={vi.fn()}
      />,
    );
    const activeBtn = screen.getByText("Active").closest("button");
    expect(activeBtn).toHaveAttribute("aria-current", "true");
    const inactiveBtn = screen.getByText("Inactive").closest("button");
    expect(inactiveBtn).not.toHaveAttribute("aria-current");
  });

  it("calls onSelectSession with the session id when clicked", async () => {
    const onSelect = vi.fn();
    const sessions = [makeSession({ session_id: "sess-abc", title: "Click me" })];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={onSelect}
      />,
    );
    await userEvent.click(screen.getByText("Click me"));
    expect(onSelect).toHaveBeenCalledWith("sess-abc");
  });

  it("shows loading skeleton when isLoading is true", () => {
    render(
      <SkillSessionPanel
        sessions={[]}
        activeSessionId={null}
        isLoading={true}
        onSelectSession={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Loading sessions")).toBeInTheDocument();
  });

  it("shows empty state when no sessions", () => {
    render(
      <SkillSessionPanel
        sessions={[]}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={vi.fn()}
      />,
    );
    expect(screen.getByText(/no previous sessions/i)).toBeInTheDocument();
  });

  it("falls back to session ID prefix when title is null", () => {
    const sessions = [makeSession({ session_id: "abcdef12-xxxx", title: null })];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={vi.fn()}
      />,
    );
    expect(screen.getByText(/Session abcdef12/)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // session-delete on the SKILL-level panel (extending 1.17 to the left sidebar)
  // ---------------------------------------------------------------------------

  it("renders a trash button on owner rows when onDelete is provided", () => {
    const sessions = [
      makeSession({ session_id: "s-own", title: "Mine", is_owner: true }),
      makeSession({ session_id: "s-team", title: "Theirs", is_owner: false }),
    ];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /delete mine/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /delete theirs/i }),
    ).toBeNull();
  });

  it("does not render any trash button when onDelete is omitted", () => {
    const sessions = [makeSession({ session_id: "s-own", title: "Mine", is_owner: true })];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /delete mine/i }),
    ).toBeNull();
  });

  it("calls onDelete with the session id when the trash button is clicked, without selecting the row", async () => {
    const onDelete = vi.fn();
    const onSelect = vi.fn();
    const sessions = [makeSession({ session_id: "s-target", title: "Goodbye", is_owner: true })];
    render(
      <SkillSessionPanel
        sessions={sessions}
        activeSessionId={null}
        isLoading={false}
        onSelectSession={onSelect}
        onDelete={onDelete}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /delete goodbye/i }));
    expect(onDelete).toHaveBeenCalledWith("s-target");
    // Critical: clicking the trash must not also fire row-selection (would
    // navigate to the very session we're deleting, breaking active-session
    // URL clear logic in the parent).
    expect(onSelect).not.toHaveBeenCalled();
  });
});
