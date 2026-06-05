// StandaloneToolCallCard — audit-view tool-call rendering tests.
//
// The contract (post-2026-06-03 refactor):
//  - Tool result parses as the send_a2ui_json_to_client envelope → mount
//    A2UIRenderer (mocked here) with the validated message array, plus a
//    Raw JSON disclosure.
//  - Tool is send_a2ui_json_to_client but the result is an SDK error
//    envelope → render the "A2UI validation failed" panel.
//  - Anything else → fall back to InputOutputCard which now renders
//    the input and output as A2UI Cards via JsonAsA2UICard (the user
//    no longer wants raw `<pre>` JSON in the audit view).

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
    // The A2UI envelope path renders the A2UIRenderer with surface id
    // ``audit-invoice-extractor-1``. There may be additional
    // A2UIRenderer nodes from InputOutputCard's JsonAsA2UICard for the
    // input args (post-refactor — see contract above) so we query for
    // the specific surface id rather than asserting "exactly one".
    const renderers = screen.queryAllByTestId("a2ui-renderer");
    const envelope = renderers.find(
      (r) => r.getAttribute("data-fallback-surface-id") === "audit-invoice-extractor-1",
    );
    expect(envelope).toBeTruthy();
    expect(envelope?.getAttribute("data-message-count")).toBe("2");
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
    // At least one A2UIRenderer should be present — the envelope render.
    expect(screen.queryAllByTestId("a2ui-renderer").length).toBeGreaterThan(0);
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
    // Note: with the InputOutputCard fallback now rendering its input
    // and output via JsonAsA2UICard, A2UIRenderer test-ids may appear
    // even when the primary envelope path failed validation. We assert
    // the error panel is present rather than absence of a2ui-renderer.
    expect(
      screen.getAllByText(/Missing required property/).length,
    ).toBeGreaterThan(0);
  });

  it("falls back to InputOutputCard for non-A2UI tools (rendered via JsonAsStructuredCard)", () => {
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
    // The audit view no longer renders raw `<pre>` JSON. The tool
    // name is still the InputOutputCard title; the input/output
    // payloads render via JsonAsStructuredCard + DefinitionList
    // (Friction 6 fix replaced JsonAsA2UICard at this seam).
    expect(screen.queryByText("Raw JSON")).toBeNull();
    expect(screen.getByText("transfer_to_validator")).toBeTruthy();
    // The structured card surfaces the scalar field names.
    expect(screen.getByText(/target/i)).toBeTruthy();
    expect(screen.getByText(/ok/i)).toBeTruthy();
  });
});
