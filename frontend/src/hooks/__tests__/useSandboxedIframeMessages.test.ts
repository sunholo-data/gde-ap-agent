/**
 * Tests for useSandboxedIframeMessages.
 *
 * Covers:
 *   - Message from the correct iframe window → onMessage called
 *   - Message from a different window → onMessage NOT called (window-identity auth)
 *   - sourceFilter: matching source field → onMessage called
 *   - sourceFilter: non-matching source field → onMessage NOT called
 *   - Cleanup: listener removed on unmount
 */

import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSandboxedIframeMessages } from "@/hooks/useSandboxedIframeMessages";

function makeIframeRef(contentWindow: Window | null = null) {
  const iframe = { contentWindow } as HTMLIFrameElement;
  return { current: iframe };
}

function fireMessage(source: Window | null, data: unknown) {
  const event = new MessageEvent("message", { data, source: source as MessageEventSource | null });
  window.dispatchEvent(event);
}

describe("useSandboxedIframeMessages", () => {
  const onMessage = vi.fn();
  const fakeWindow = {} as Window;

  beforeEach(() => {
    onMessage.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls onMessage when source matches iframe contentWindow", () => {
    const ref = makeIframeRef(fakeWindow);
    renderHook(() =>
      useSandboxedIframeMessages(ref, { onMessage }),
    );

    fireMessage(fakeWindow, { type: "ui/ready" });
    expect(onMessage).toHaveBeenCalledOnce();
    expect(onMessage).toHaveBeenCalledWith({
      type: "ui/ready",
      payload: { type: "ui/ready" },
    });
  });

  it("ignores messages from a different window (window-identity auth)", () => {
    const ref = makeIframeRef(fakeWindow);
    const otherWindow = {} as Window;
    renderHook(() =>
      useSandboxedIframeMessages(ref, { onMessage }),
    );

    fireMessage(otherWindow, { type: "ui/ready" });
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("ignores messages when contentWindow is null", () => {
    const ref = makeIframeRef(null);
    renderHook(() =>
      useSandboxedIframeMessages(ref, { onMessage }),
    );

    fireMessage(fakeWindow, { type: "ui/ready" });
    expect(onMessage).not.toHaveBeenCalled();
  });

  describe("sourceFilter", () => {
    it("accepts messages where data.source matches sourceFilter", () => {
      const ref = makeIframeRef(fakeWindow);
      renderHook(() =>
        useSandboxedIframeMessages(ref, { sourceFilter: "my-app", onMessage }),
      );

      fireMessage(fakeWindow, { source: "my-app", type: "ping" });
      expect(onMessage).toHaveBeenCalledOnce();
    });

    it("rejects messages where data.source does not match sourceFilter", () => {
      const ref = makeIframeRef(fakeWindow);
      renderHook(() =>
        useSandboxedIframeMessages(ref, { sourceFilter: "my-app", onMessage }),
      );

      fireMessage(fakeWindow, { source: "other-app", type: "ping" });
      expect(onMessage).not.toHaveBeenCalled();
    });

    it("rejects messages with no source field when sourceFilter is set", () => {
      const ref = makeIframeRef(fakeWindow);
      renderHook(() =>
        useSandboxedIframeMessages(ref, { sourceFilter: "my-app", onMessage }),
      );

      fireMessage(fakeWindow, { type: "ping" });
      expect(onMessage).not.toHaveBeenCalled();
    });
  });

  it("removes the event listener on unmount", () => {
    const ref = makeIframeRef(fakeWindow);
    const { unmount } = renderHook(() =>
      useSandboxedIframeMessages(ref, { onMessage }),
    );

    unmount();
    fireMessage(fakeWindow, { type: "after-unmount" });
    expect(onMessage).not.toHaveBeenCalled();
  });
});
