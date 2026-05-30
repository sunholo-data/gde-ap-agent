// A2UI v0.9 renderer for the inline-in-chat path.
//
// Each MessageBubble that produces inline A2UI (skills WITHOUT a routed
// surface) instantiates its own A2UIRenderer with the validated v0.9 message
// array from the SDK envelope. The renderer owns a per-bubble MessageProcessor
// and SurfaceModel — its lifetime is the bubble's lifetime, so cross-bubble
// state cannot bleed.
//
// Routed-surface skills (workspace, sidebar, modal) don't use this component;
// they dispatch into SurfaceRegistry and the named A2UISurfaceMount renders
// the SurfaceModel directly from there.
//
// Wire-format contract:
//   - `messages` is the SDK-validated array of v0.9 messages (createSurface,
//     updateComponents, updateDataModel, deleteSurface).
//   - The first message SHOULD be a createSurface; if missing, we synthesize
//     one with basicCatalog so the demo survives LLM message-ordering drift.
//   - If parsing/dispatch fails, we render a debug fallback rather than
//     crash the bubble.

"use client";

import {
  A2uiSurface,
  basicCatalog,
  type ReactComponentImplementation,
} from "@a2ui/react/v0_9";
import { injectStyles } from "@a2ui/react/styles";
import {
  MessageProcessor,
  type A2uiMessage,
  type SurfaceModel,
} from "@a2ui/web_core/v0_9";
import { useEffect, useMemo, useState } from "react";

let stylesInjected = false;
function ensureStyles() {
  if (stylesInjected || typeof window === "undefined") return;
  stylesInjected = true;
  injectStyles();
}

export interface A2UIRendererProps {
  /** v0.9 message array as returned by the SDK validator. */
  messages: unknown;
  /**
   * Inline-in-chat surfaces are anonymous — the SDK assigns whatever
   * surfaceId the LLM emitted on createSurface. If the LLM forgot to emit
   * createSurface AND the renderer must auto-create one, we use this id.
   * Defaults to a unique-ish "inline" id; routed surfaces should not use
   * this component.
   */
  fallbackSurfaceId?: string;
  /**
   * Optional action handler — fired when a button/input in the rendered tree
   * dispatches an action. The MessageBubble wires this to its chat-send
   * callback so user clicks flow back as new messages.
   */
  onAction?: (action: { name: string; sourceComponentId: string; context: Record<string, unknown> }) => void;
}

function isMessageArray(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every((m) => m && typeof m === "object");
}

function pickSurfaceId(messages: Record<string, unknown>[], fallback: string): string {
  for (const msg of messages) {
    for (const key of ["createSurface", "updateComponents", "updateDataModel", "deleteSurface"] as const) {
      const payload = msg[key];
      if (payload && typeof payload === "object" && "surfaceId" in payload) {
        const id = (payload as { surfaceId?: unknown }).surfaceId;
        if (typeof id === "string" && id.length > 0) return id;
      }
    }
  }
  return fallback;
}

export function A2UIRenderer({ messages, fallbackSurfaceId, onAction }: A2UIRendererProps) {
  useEffect(() => {
    ensureStyles();
  }, []);

  // Build a per-bubble processor + SurfaceModel once and re-feed only if the
  // message array identity changes. The bubble is keyed by message.id in
  // MessageBubble, so re-feeds in practice mean React strict-mode double-run.
  const [surface, setSurface] = useState<SurfaceModel<ReactComponentImplementation> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const processor = useMemo(
    () => new MessageProcessor<ReactComponentImplementation>([basicCatalog]),
    // One processor per renderer instance; the bubble keys the renderer.
    // We intentionally do NOT depend on `messages` here.
    [],
  );

  // Wire actions: subscribe once per processor; the model fan-out reaches
  // every surface inside it.
  useEffect(() => {
    if (!onAction) return;
    const sub = processor.model.onAction.subscribe((action) => {
      onAction({
        name: action.name,
        sourceComponentId: action.sourceComponentId,
        context: action.context,
      });
    });
    return () => sub.unsubscribe();
  }, [processor, onAction]);

  useEffect(() => {
    if (!isMessageArray(messages)) {
      setError(`A2UI payload is not a v0.9 message array: ${JSON.stringify(messages).slice(0, 200)}`);
      return;
    }

    const surfaceId = pickSurfaceId(messages, fallbackSurfaceId ?? "inline");
    const firstHasCreate = "createSurface" in messages[0];
    const exists = processor.model.getSurface(surfaceId) !== undefined;

    try {
      if (!firstHasCreate && !exists) {
        if (process.env.NODE_ENV !== "production") {
          console.warn(
            `[A2UIRenderer] inline surface "${surfaceId}" received update ` +
              `without prior createSurface — auto-creating with basicCatalog.`,
          );
        }
        processor.processMessages([
          {
            version: "v0.9",
            createSurface: { surfaceId, catalogId: basicCatalog.id },
          } as A2uiMessage,
        ]);
      }
      // The SDK validator already accepted these messages on the backend;
      // cast at the boundary since the typed union is wider than what
      // arrives at runtime.
      processor.processMessages(messages as unknown as A2uiMessage[]);
      const model = processor.model.getSurface(surfaceId) ?? null;
      setSurface(model);
      setError(null);
    } catch (err) {
      setError(`A2UI processMessages failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [processor, messages, fallbackSurfaceId]);

  if (error) {
    return (
      <pre
        data-testid="a2ui-fallback"
        className="whitespace-pre-wrap rounded-md border bg-muted p-3 text-xs"
      >
        {error}
        {"\n\n"}
        {JSON.stringify(messages, null, 2)}
      </pre>
    );
  }

  if (!surface) return null;

  return (
    <div className="a2ui-surface rounded-md border p-3" data-surface-id={surface.id}>
      <A2uiSurface surface={surface} />
    </div>
  );
}
