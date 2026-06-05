import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageBubble } from "../MessageBubble";
import type { SkillMessage } from "@/hooks/useSkillAgent";
import { BRANDING } from "@/lib/branding";

vi.mock("@/components/protocols/A2UIRenderer", () => ({
  A2UIRenderer: () => <div data-testid="a2ui-renderer" />,
}));
const mcpRouterMock = vi.fn();
vi.mock("@/components/protocols/MCPAppToolCallRouter", () => ({
  MCPAppToolCallRouter: (props: Record<string, unknown>) => {
    mcpRouterMock(props);
    return <div data-testid="mcp-app-router" />;
  },
}));

const noOp = vi.fn();
const noopNavigate = vi.fn();

function botMsg(content = "Hello from bot"): SkillMessage {
  return { id: "bot-1", role: "assistant", content };
}

function userMsg(content = "Hello from user"): SkillMessage {
  return { id: "user-1", role: "user", content };
}

const baseProps = {
  skillId: "test-skill",
  userInitial: "M",
  userDisplayName: "Mark",
  toolCalls: [],
  navigateToBlock: noopNavigate,
  onAction: noOp,
};

describe("MessageBubble — bot variant", () => {
  it("renders message content", () => {
    render(<MessageBubble message={botMsg()} {...baseProps} />);
    expect(screen.getByText(/hello from bot/i)).toBeInTheDocument();
  });

  it("shows skill name in header", () => {
    render(<MessageBubble message={botMsg()} {...baseProps} />);
    expect(screen.getByText("test-skill")).toBeInTheDocument();
  });

  it("applies a left border to the bot bubble", () => {
    const { container } = render(<MessageBubble message={botMsg()} {...baseProps} />);
    // border class uses CSS var (border-primary/50) — check the element has any border-l class
    const bubble = container.querySelector("[class*='border-l-']");
    expect(bubble).toBeInTheDocument();
  });

  it("renders bot avatar image with branded alt text", () => {
    render(<MessageBubble message={botMsg()} {...baseProps} />);
    expect(screen.getByRole("img", { name: BRANDING.appName })).toBeInTheDocument();
  });

  it("shows a timestamp", () => {
    render(<MessageBubble message={botMsg()} {...baseProps} />);
    // Timestamp is in AM/PM format — just check something time-like exists
    expect(document.body.textContent).toMatch(/\d{1,2}:\d{2}/);
  });
});

describe("MessageBubble — user variant", () => {
  it("renders message content", () => {
    render(<MessageBubble message={userMsg()} {...baseProps} />);
    expect(screen.getByText(/hello from user/i)).toBeInTheDocument();
  });

  it("shows user display name in header", () => {
    render(<MessageBubble message={userMsg()} {...baseProps} />);
    expect(screen.getByText("Mark")).toBeInTheDocument();
  });

  it("applies a left accent border to user bubbles", () => {
    // Theme-tokenized after the avatar restyle (was border-teal-500).
    const { container } = render(<MessageBubble message={userMsg()} {...baseProps} />);
    expect(container.querySelector('[class*="border-l-"][class*="border-primary"]')).toBeInTheDocument();
  });

  it("renders initial avatar letter", () => {
    render(<MessageBubble message={userMsg()} {...baseProps} />);
    expect(screen.getByText("M")).toBeInTheDocument();
  });
});

describe("MessageBubble — tool call chips", () => {
  it("renders running tool call chip with tool name", () => {
    const toolCalls = [{ id: "tc-1", name: "web_search", status: "running" as const }];
    render(<MessageBubble message={botMsg()} {...baseProps} toolCalls={toolCalls} />);
    expect(screen.getByText("web_search")).toBeInTheDocument();
  });

  it("truncates long tool names to 32 chars", () => {
    const longName = "a".repeat(40);
    const toolCalls = [{ id: "tc-1", name: longName, status: "running" as const }];
    render(<MessageBubble message={botMsg()} {...baseProps} toolCalls={toolCalls} />);
    expect(screen.getByText("a".repeat(32) + "…")).toBeInTheDocument();
  });
});

describe("MessageBubble — A2UI tool delivery", () => {
  it("renders A2UIRenderer for send_a2ui_json_to_client result", () => {
    const payload = { component: "form", fields: [] };
    const toolCalls = [
      {
        id: "tc-a2ui",
        name: "send_a2ui_json_to_client",
        status: "success" as const,
        resultContent: JSON.stringify({ validated_a2ui_json: payload }),
      },
    ];
    const { container } = render(
      <MessageBubble message={botMsg()} {...baseProps} toolCalls={toolCalls} />,
    );
    // A2UIRenderer mocked to data-testid="a2ui-renderer"
    expect(container.querySelector("[data-testid='a2ui-renderer']")).toBeInTheDocument();
  });

  it("does not render ToolCallChip for send_a2ui_json_to_client", () => {
    const toolCalls = [
      {
        id: "tc-a2ui",
        name: "send_a2ui_json_to_client",
        status: "success" as const,
        resultContent: JSON.stringify({ validated_a2ui_json: { component: "table" } }),
      },
    ];
    render(<MessageBubble message={botMsg()} {...baseProps} toolCalls={toolCalls} />);
    // ToolCallChip shows the tool name — should NOT appear for A2UI calls
    expect(screen.queryByText("send_a2ui_json_to_client")).not.toBeInTheDocument();
  });

  it("renders ToolCallChip for non-A2UI tool calls", () => {
    const toolCalls = [
      { id: "tc-1", name: "web_search", status: "success" as const },
    ];
    render(<MessageBubble message={botMsg()} {...baseProps} toolCalls={toolCalls} />);
    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(screen.queryByTestId("a2ui-renderer")).not.toBeInTheDocument();
  });

  it("does not render A2UIRenderer when resultContent is missing", () => {
    const toolCalls = [
      { id: "tc-a2ui", name: "send_a2ui_json_to_client", status: "running" as const },
    ];
    const { container } = render(
      <MessageBubble message={botMsg()} {...baseProps} toolCalls={toolCalls} />,
    );
    expect(container.querySelector("[data-testid='a2ui-renderer']")).not.toBeInTheDocument();
  });
});

describe("MessageBubble — JSON-only text rendered as A2UI Card", () => {
  // When an agent (any agent — orchestrator, sub-agent, extractor)
  // returns JSON as its final text, render it as a styled Card instead
  // of a code block. The agent doesn't need to emit A2UI — the frontend
  // turns the JSON into a v0.9 message array via JsonCardBuilder and
  // feeds it through the existing A2UIRenderer path. This is the user-
  // visible fix for the "JSON blob in chat" anti-pattern.

  it("renders JSON-only text as a Card (no raw JSON in the DOM)", () => {
    const jsonOnly = JSON.stringify({ vendor_name: "Acme GmbH", total: 8500 });
    const { container } = render(<MessageBubble message={botMsg(jsonOnly)} {...baseProps} />);
    // The renderer was invoked (mocked → testid).
    expect(container.querySelector("[data-testid='a2ui-renderer']")).toBeInTheDocument();
    // The raw JSON text body is NOT rendered — only the Card.
    expect(screen.queryByText(/vendor_name/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Acme GmbH/)).not.toBeInTheDocument();
  });

  it("does NOT render a Card for prose that merely contains a JSON snippet", () => {
    // The trigger is unambiguous JSON-only text; prose with embedded
    // JSON must continue to render as markdown so the user sees the
    // surrounding sentences.
    const proseWithJson =
      'I extracted the invoice. The result is: {"vendor":"Acme"}. Please review.';
    const { container } = render(
      <MessageBubble message={botMsg(proseWithJson)} {...baseProps} />,
    );
    expect(container.querySelector("[data-testid='a2ui-renderer']")).not.toBeInTheDocument();
    expect(screen.getByText(/I extracted the invoice/)).toBeInTheDocument();
  });

  it("prefers an existing inline A2UI tool result over the JSON-derived Card", () => {
    // If the agent already emitted A2UI directly, that takes priority —
    // we don't double up. The JSON text body is suppressed.
    const jsonOnly = JSON.stringify({ vendor_name: "Acme GmbH" });
    const toolCalls = [
      {
        id: "tc-a2ui",
        name: "send_a2ui_json_to_client",
        status: "success" as const,
        resultContent: JSON.stringify({
          validated_a2ui_json: [{ version: "v0.9", createSurface: { surfaceId: "chat" } }],
          surface_id: "chat",
        }),
      },
    ];
    const { container } = render(
      <MessageBubble message={botMsg(jsonOnly)} {...baseProps} toolCalls={toolCalls} />,
    );
    // Exactly one A2UIRenderer mount — the one from the real tool call.
    const renderers = container.querySelectorAll("[data-testid='a2ui-renderer']");
    expect(renderers).toHaveLength(1);
    expect(screen.queryByText(/vendor_name/)).not.toBeInTheDocument();
  });
});

describe("isLikelyJsonOnly", () => {
  it("returns true for a JSON object string", async () => {
    const { isLikelyJsonOnly } = await import("../MessageBubble");
    expect(isLikelyJsonOnly('{"a":1}')).toBe(true);
  });

  it("returns true for a JSON array string", async () => {
    const { isLikelyJsonOnly } = await import("../MessageBubble");
    expect(isLikelyJsonOnly("[1, 2, 3]")).toBe(true);
  });

  it("returns false for prose that contains a JSON snippet", async () => {
    const { isLikelyJsonOnly } = await import("../MessageBubble");
    expect(isLikelyJsonOnly('Here is the data: {"a":1}')).toBe(false);
  });

  it("returns false for empty string", async () => {
    const { isLikelyJsonOnly } = await import("../MessageBubble");
    expect(isLikelyJsonOnly("")).toBe(false);
    expect(isLikelyJsonOnly("   ")).toBe(false);
  });

  it("returns false for malformed JSON", async () => {
    const { isLikelyJsonOnly } = await import("../MessageBubble");
    expect(isLikelyJsonOnly('{"unclosed":')).toBe(false);
  });
});

describe("MessageBubble — MCP App tool routing", () => {
  it("invokes MCPAppToolCallRouter with non-A2UI tool calls that have resultContent", () => {
    mcpRouterMock.mockClear();
    const toolCalls = [
      {
        id: "tc-show-map",
        name: "show-map",
        status: "success" as const,
        resultContent: JSON.stringify({ content: [{ type: "text", text: "ok" }] }),
      },
      {
        id: "tc-a2ui",
        name: "send_a2ui_json_to_client",
        status: "success" as const,
        resultContent: JSON.stringify({ validated_a2ui_json: { component: "x" } }),
      },
    ];
    render(
      <MessageBubble
        message={botMsg()}
        {...baseProps}
        toolCalls={toolCalls}
        mcpServerIds={["map-server"]}
      />,
    );
    expect(mcpRouterMock).toHaveBeenCalledOnce();
    const props = mcpRouterMock.mock.calls[0][0] as {
      toolCalls: Array<{ id: string }>;
      mcpServerIds: readonly string[];
    };
    // A2UI tool is filtered out before hitting the router; show-map remains.
    expect(props.toolCalls.map((tc) => tc.id)).toEqual(["tc-show-map"]);
    expect(props.mcpServerIds).toEqual(["map-server"]);
  });

  it("does NOT invoke MCPAppToolCallRouter when no candidates have resultContent", () => {
    mcpRouterMock.mockClear();
    const toolCalls = [
      // running tool — no resultContent yet
      { id: "tc-running", name: "show-map", status: "running" as const },
    ];
    render(
      <MessageBubble
        message={botMsg()}
        {...baseProps}
        toolCalls={toolCalls}
        mcpServerIds={["map-server"]}
      />,
    );
    expect(mcpRouterMock).not.toHaveBeenCalled();
  });

  it("forwards onChatMessage prop to MCPAppToolCallRouter", () => {
    mcpRouterMock.mockClear();
    const onChatMessage = vi.fn();
    const toolCalls = [
      {
        id: "tc-show-map",
        name: "show-map",
        status: "success" as const,
        resultContent: JSON.stringify({ content: [] }),
      },
    ];
    render(
      <MessageBubble
        message={botMsg()}
        {...baseProps}
        toolCalls={toolCalls}
        mcpServerIds={["map-server"]}
        onChatMessage={onChatMessage}
      />,
    );
    const props = mcpRouterMock.mock.calls[0][0] as {
      onChatMessage: (s: string) => void;
    };
    expect(props.onChatMessage).toBe(onChatMessage);
  });
});
