import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatMessageList } from "../ChatMessageList";
import type { SkillMessage } from "@/hooks/useSkillAgent";

// A2UIRenderer and MCPAppToolCallRouter mount external surfaces — stub them.
vi.mock("@/components/protocols/A2UIRenderer", () => ({
  A2UIRenderer: () => <div data-testid="a2ui-renderer" />,
}));
vi.mock("@/components/protocols/MCPAppToolCallRouter", () => ({
  MCPAppToolCallRouter: () => <div data-testid="mcp-app-router" />,
}));

const noOp = vi.fn();

const baseProps = {
  toolCalls: [],
  thinkingContent: "",
  isThinking: false,
  isLoading: false,
  error: null,
  skillId: "my-skill",
  userInitial: "M",
  userDisplayName: "Mark",
  onAction: noOp,
};

function msg(id: string, role: SkillMessage["role"], content: string): SkillMessage {
  return { id, role, content };
}

describe("ChatMessageList", () => {
  it("renders a placeholder when there are no messages", () => {
    render(<ChatMessageList messages={[]} {...baseProps} />);
    expect(screen.getByText(/send a message/i)).toBeInTheDocument();
  });

  it("maps N messages to N bubbles", () => {
    const messages = [
      msg("u1", "user", "Hi"),
      msg("a1", "assistant", "Hello!"),
      msg("u2", "user", "How are you?"),
    ];
    render(<ChatMessageList messages={messages} {...baseProps} />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello!")).toBeInTheDocument();
    expect(screen.getByText("How are you?")).toBeInTheDocument();
  });

  it("shows TypingIndicator dots when isLoading with no assistant message yet", () => {
    const messages = [msg("u1", "user", "Hello")];
    const { container } = render(
      <ChatMessageList messages={messages} {...baseProps} isLoading={true} />,
    );
    // TypingIndicator has three animate-bounce dots when no tool is running
    expect(container.querySelectorAll(".animate-bounce")).toHaveLength(3);
  });

  it("shows tool name in TypingIndicator when a tool call is running", () => {
    const messages = [msg("u1", "user", "Hello")];
    render(
      <ChatMessageList
        messages={messages}
        {...baseProps}
        isLoading={true}
        toolCalls={[{ id: "tc1", name: "web_search", status: "running" }]}
      />,
    );
    expect(screen.getByText("web_search")).toBeInTheDocument();
  });

  it("shows StreamingBubble when last message is assistant and isLoading", () => {
    const messages = [
      msg("u1", "user", "Hello"),
      msg("a1", "assistant", "I am typing..."),
    ];
    const { container } = render(
      <ChatMessageList messages={messages} {...baseProps} isLoading={true} />,
    );
    // StreamingBubble has the animate-pulse cursor
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows ContextBanner when activeDocumentContext is provided", () => {
    render(
      <ChatMessageList
        messages={[]}
        {...baseProps}
        activeDocumentContext={{ folderName: "Q1 Docs", docCount: 5 }}
      />,
    );
    expect(screen.getByText(/q1 docs/i)).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("does not show ContextBanner when activeDocumentContext is undefined", () => {
    render(<ChatMessageList messages={[]} {...baseProps} />);
    expect(screen.queryByText(/analyzing/i)).toBeNull();
  });

  it("renders the errorBanner slot", () => {
    render(
      <ChatMessageList
        messages={[]}
        {...baseProps}
        errorBanner={<div>Stream error!</div>}
      />,
    );
    expect(screen.getByText("Stream error!")).toBeInTheDocument();
  });

  it("Bug G (chat-history-deep-fixes-3): an unparented tool call must NOT broadcast to every assistant bubble", () => {
    // Reproduces the user's report: "when we do a tool call, all chat
    // windows appear with the tool/results — not just the last one, that
    // did the toolcall."
    //
    // Pre-fix: ChatMessageList builds toolCallsByParent and falls back
    // every bubble that doesn't have its own keyed tool calls to the
    // SAME `__unparented__` array, so every assistant bubble renders the
    // same chip. Post-fix: unparented calls attach to the most recent
    // assistant message only (or none if no assistant exists yet).
    const messages = [
      msg("u1", "user", "first question"),
      msg("a1", "assistant", "first answer"),
      msg("u2", "user", "second question"),
      msg("a2", "assistant", "second answer"),
    ];
    render(
      <ChatMessageList
        messages={messages}
        {...baseProps}
        toolCalls={[
          // No parentMessageId — this is the bug class.
          { id: "tc-orphan", name: "web_search", status: "success" },
        ]}
      />,
    );

    // ToolCallChip renders the tool name as visible text. Pre-fix this
    // assertion fails because "web_search" appears in BOTH a1 and a2
    // bubbles (every non-keyed bubble falls back to __unparented__).
    const occurrences = screen.queryAllByText("web_search");
    expect(occurrences).toHaveLength(1);
  });
});
