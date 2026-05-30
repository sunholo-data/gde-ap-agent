// MULTI-SURFACE-A2UI — A2UISurfaceMount (v0.9 native)
//
// Renders a named A2UI surface using the SurfaceModel that the
// SurfaceRegistry keeps for `surfaceId`. The registry's per-surface
// MessageProcessor owns the model lifecycle; this component is a thin
// render of `<A2uiSurface>` plus mount registration so the dispatcher
// knows the surface exists in the DOM.
//
// Sprint 2.10 (sibling of MCP Apps' ui/update-model-context):
// subscribes to `surface.onAction` and POSTs the A2uiClientAction to
// `/api/sessions/{id}/surface-action`. The backend writes the action
// into ADK session state under
// `a2ui_surface_context.{surfaceId}.lastAction`, where the
// InstructionProvider reads it on the next agent turn. The action
// loop is OPTIONAL per skill — backend gates require
// `tool_configs.a2ui.allow_surface_context_writes: true`; without it
// the POST returns 403 and we drop silently (logged in dev).
//
// useLayoutEffect (not useEffect) for registration — completes before
// paint, so a dispatch arriving in the same tick the mount layouts
// already finds the surface in the registry.

"use client";

import { useEffect, useLayoutEffect, useRef } from "react";
import { A2uiSurface } from "@a2ui/react/v0_9";
import { fetchWithAuth } from "@/lib/apiClient";
import {
  type SurfacePolicy,
  useSurfaceRegistry,
  useSurfaceState,
} from "@/providers/SurfaceRegistry";

export interface A2UISurfaceMountProps {
  surfaceId: string;
  /** Override individual policy fields; merged onto the default for `surfaceId`. */
  policy?: Partial<SurfacePolicy>;
  /** Tailwind / layout classes for the mount's outer div. */
  className?: string;
  /**
   * Current chat session id. Required for the sprint-2.10 action POST
   * (the endpoint URL embeds it). When `null` (no session yet — fresh
   * chat before first send), action dispatch is skipped — there's
   * nowhere to write the namespaced state. The frontend's snapshot
   * push path still works through `forwardedProps`.
   */
  sessionId?: string | null;
}

export function A2UISurfaceMount({
  surfaceId,
  policy,
  className,
  sessionId,
}: A2UISurfaceMountProps) {
  const ref = useRef<HTMLDivElement>(null);
  const registry = useSurfaceRegistry();
  const state = useSurfaceState(surfaceId);

  useLayoutEffect(() => {
    registry.register(surfaceId, ref, policy);
    return () => {
      registry.unregister(surfaceId);
    };
  }, [surfaceId, policy, registry]);

  // Subscribe to surface actions and POST each one to the backend's
  // surface-action endpoint. Re-subscribes whenever the SurfaceModel
  // identity changes (clearSurface → new createSurface).
  useEffect(() => {
    if (!state?.surface) return;
    if (!sessionId) return;
    const sub = state.surface.onAction.subscribe(async (action) => {
      try {
        const res = await fetchWithAuth(
          `/api/proxy/api/sessions/${encodeURIComponent(sessionId)}/surface-action`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              surfaceId,
              action: {
                name: action.name,
                sourceComponentId: action.sourceComponentId,
                timestamp: action.timestamp,
                context: action.context,
              },
            }),
          },
        );
        if (!res.ok && process.env.NODE_ENV !== "production") {
          // 403 is the expected response when the skill hasn't opted in;
          // we log but don't surface to the user.
          const detail = await res.text().catch(() => "");
          console.info(
            `[A2UISurfaceMount] surface-action POST returned ${res.status} for surface "${surfaceId}"`,
            detail,
          );
        }
      } catch (err) {
        if (process.env.NODE_ENV !== "production") {
          console.warn(
            `[A2UISurfaceMount] surface-action POST failed for surface "${surfaceId}":`,
            err,
          );
        }
      }
    });
    return () => sub.unsubscribe();
  }, [state?.surface, surfaceId, sessionId]);

  return (
    <div ref={ref} className={className} data-surface={surfaceId}>
      {state?.surface && <A2uiSurface surface={state.surface} />}
    </div>
  );
}
