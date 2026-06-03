// StandaloneToolCallCard — audit-view tool-call rendering tests.
//
// The contract:
//  - Tool result parses as the send_a2ui_json_to_client envelope → mount
//    A2UIRenderer (mocked here) with the validated message array, plus a
//    Raw JSON disclosure.
//  - Tool is send_a2ui_json_to_client but the result is an SDK error
//    envelope → render the "A2UI validation failed" panel.
//  - Anything else → fall back to InputOutputCard (raw <pre> blocks).

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Mock A2UIRenderer so we don't pull the v0.9 SDK into JSDOM. The mock
// just records the props we'd pass through.
vi.mock("@/components/protocols/A2UIRenderer", () => ({
  A2UIRenderer: ({
    messages,
    fallbackSurfaceId,
  }: {
    messages: unknown;
    fallbackSurfaceId?: string;
  }) => (
    <div
      data-testid="a2ui-renderer"
      data-fallback-surface-id={fallbackSurfaceId ?? ""}
      data-message-count={Array.isArray(messages) ? messages.length : -1}
    />
  ),
}));

import { StandaloneToolCallCard } from "../StandaloneToolCallCard";

const validEnvelope = {
  validated_a2ui_json: [
    {
      version: "v0.9",
      createSurface: {
        surfaceId: "chat",
        catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json",
      },
    },
    {
      version: "v0.9",
      updateComponents: { surfaceId: "chat", components: [] },
    },
  ],
  mime_type: "application/json+a2ui",
  surface_id: "workspace",
  update_mode: "replace",
};

describe("StandaloneToolCallCard", () => {
  it("renders A2UIRenderer when result is a valid A2UI envelope", () => {
    render(
      <StandaloneToolCallCard
        index={1}
        toolCall={{
          name: "send_a2ui_json_to_client",
          args: JSON.stringify({ a2ui_json: "[{\"v\":1}]" }),
          result: validEnvelope,
        }}
        skillId="invoice-extractor"
      />,
    );
    const renderer = screen.getByTestId("a2ui-renderer");
    expect(renderer.getAttribute("data-message-count")).toBe("2");
    expect(renderer.getAttribute("data-fallback-surface-id")).toBe(
      "audit-invoice-extractor-1",
    );
    // Raw JSON disclosure is present but collapsed.
    expect(screen.getByText("Raw JSON")).toBeTruthy();
  });

  it("handles a result delivered as a JSON string", () => {
    render(
      <StandaloneToolCallCard
        index={2}
        toolCall={{
          name: "send_a2ui_json_to_client",
          args: "{}",
          result: JSON.stringify(validEnvelope),
        }}
        skillId="x"
      />,
    );
    expect(screen.getByTestId("a2ui-renderer")).toBeTruthy();
  });

  it("renders an error panel for an A2UI error envelope", () => {
    render(
      <StandaloneToolCallCard
        index={3}
        toolCall={{
          name: "send_a2ui_json_to_client",
          args: "{}",
          result: {
            error: "ValidationError",
            message: "Missing required property\n - messages[1].updateComponents",
          },
        }}
        skillId="x"
      />,
    );
    expect(screen.getByText(/A2UI validation failed/i)).toBeTruthy();
    expect(screen.queryByTestId("a2ui-renderer")).toBeNull();
    // The error text appears both in the error panel and (when expanded) in
    // the Raw JSON disclosure — `getAllByText` lets us assert presence
    // without coupling to the disclosure's open/closed state.
    expect(
      screen.getAllByText(/Missing required property/).length,
    ).toBeGreaterThan(0);
  });

  it("falls back to InputOutputCard for non-A2UI tools", () => {
    render(
      <StandaloneToolCallCard
        index={4}
        toolCall={{
          name: "transfer_to_validator",
          args: '{"target":"validator"}',
          result: { ok: true },
        }}
        skillId="x"
      />,
    );
    expect(screen.queryByTestId("a2ui-renderer")).toBeNull();
    expect(screen.queryByText("Raw JSON")).toBeNull();
    // InputOutputCard renders the tool name as a title.
    expect(screen.getByText("transfer_to_validator")).toBeTruthy();
  });
});
