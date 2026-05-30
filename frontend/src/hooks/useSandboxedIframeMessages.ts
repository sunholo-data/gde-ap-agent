"use client";

/**
 * Centralized postMessage listener for sandboxed iframes that use
 * `sandbox="allow-scripts"` WITHOUT `allow-same-origin`.
 *
 * ## Why window-identity auth, not origin auth
 *
 * The `allow-scripts` profile (without `allow-same-origin`) produces an
 * **opaque origin** on the iframe's side — every `postMessage` arrives with
 * `event.origin === "null"`. Comparing `event.origin` against any real origin
 * will reject ALL messages; comparing against the string `"null"` is
 * dangerously permissive (any cross-origin frame can spoof it).
 *
 * The only secure authentication for this sandbox profile is:
 * ```
 * event.source === iframeRef.current.contentWindow
 * ```
 * This compares the JavaScript window-object identity, which cannot be
 * spoofed by a different browsing context.
 *
 * If you need origin-based auth, add `allow-same-origin` to your sandbox
 * attribute AND audit the CSP of the parent page. See ADR-013.
 *
 * ## Source filter
 *
 * Pass `sourceFilter` to accept only messages where `event.data.source`
 * matches a given string — useful when the iframe marks all its messages
 * with a custom `source` field (e.g. `{ source: "my-app", type: "...", ... }`).
 */

import { type RefObject, useEffect } from "react";

export interface SandboxedMessage<T = unknown> {
  type: string;
  payload: T;
}

export function useSandboxedIframeMessages<T = unknown>(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  options: {
    /**
     * Only accept messages where `event.data.source` equals this string.
     * Leave undefined to accept all messages from the iframe.
     */
    sourceFilter?: string;
    onMessage: (msg: SandboxedMessage<T>) => void;
  },
): void {
  const { sourceFilter, onMessage } = options;

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      // Auth: window-object identity (not origin — see JSDoc above)
      if (event.source !== iframeRef.current?.contentWindow) return;
      // Optional source-field filter
      if (
        sourceFilter !== undefined &&
        (event.data == null || event.data.source !== sourceFilter)
      )
        return;
      onMessage({ type: String(event.data?.type ?? ""), payload: event.data as T });
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [iframeRef, sourceFilter, onMessage]);
}
