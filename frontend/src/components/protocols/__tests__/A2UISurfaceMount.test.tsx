// M2 — A2UISurfaceMount tests
// The mount is the *layout primitive* that declares a named surface in the
// React tree. It binds its inner div ref into the SurfaceRegistry on mount
// and unregisters on unmount.

import { render } from "@testing-library/react";
import { type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { A2UISurfaceMount } from "@/components/protocols/A2UISurfaceMount";
import {
  SurfaceRegistryProvider,
  useSurfaceRegistry,
} from "@/providers/SurfaceRegistry";

function wrap(children: ReactNode) {
  return <SurfaceRegistryProvider>{children}</SurfaceRegistryProvider>;
}

describe("A2UISurfaceMount", () => {
  it("renders a div with data-surface attribute", () => {
    const { container } = render(
      wrap(<A2UISurfaceMount surfaceId="workspace" />),
    );
    const el = container.querySelector('[data-surface="workspace"]');
    expect(el).toBeTruthy();
    expect(el?.tagName).toBe("DIV");
  });

  it("forwards className to the underlying div", () => {
    const { container } = render(
      wrap(
        <A2UISurfaceMount surfaceId="workspace" className="w-1/2 bg-muted" />,
      ),
    );
    const el = container.querySelector('[data-surface="workspace"]');
    expect(el?.className).toBe("w-1/2 bg-muted");
  });

  it("registers itself with the SurfaceRegistry on mount; unregisters on unmount", () => {
    let registryHandle: ReturnType<typeof useSurfaceRegistry> | null = null;
    function Capture() {
      registryHandle = useSurfaceRegistry();
      return null;
    }

    const { unmount } = render(
      wrap(
        <>
          <Capture />
          <A2UISurfaceMount surfaceId="workspace" />
        </>,
      ),
    );

    // useLayoutEffect runs synchronously before paint — by the time render()
    // returns the registration is in place.
    expect(registryHandle).not.toBeNull();
    const mountRef = registryHandle!.getMount("workspace");
    expect(mountRef).not.toBeNull();
    expect(mountRef?.current).toBeInstanceOf(HTMLDivElement);
    expect(mountRef?.current?.getAttribute("data-surface")).toBe("workspace");

    unmount();
    // Unmount path runs the registry.unregister cleanup; can't query the
    // captured handle (provider gone), but render output is gone too.
  });

  it("returns null from getMount after the mount unmounts", () => {
    let registryHandle: ReturnType<typeof useSurfaceRegistry> | null = null;
    function Capture() {
      registryHandle = useSurfaceRegistry();
      return null;
    }

    // Render with a parent provider so the registry survives the child unmount
    const { rerender } = render(
      wrap(
        <>
          <Capture />
          <A2UISurfaceMount surfaceId="workspace" />
        </>,
      ),
    );

    expect(registryHandle!.getMount("workspace")).not.toBeNull();

    rerender(
      wrap(
        <>
          <Capture />
          {/* A2UISurfaceMount removed */}
        </>,
      ),
    );

    expect(registryHandle!.getMount("workspace")).toBeNull();
  });

  it("propagates a policy override to the registry (e.g., persistence=indefinite)", () => {
    let registryHandle: ReturnType<typeof useSurfaceRegistry> | null = null;
    function Capture() {
      registryHandle = useSurfaceRegistry();
      return null;
    }
    render(
      wrap(
        <>
          <Capture />
          <A2UISurfaceMount
            surfaceId="sidebar"
            policy={{ persistence: "indefinite" }}
          />
        </>,
      ),
    );
    expect(registryHandle!.getPolicy("sidebar").persistence).toBe("indefinite");
    // Other fields keep their defaults
    expect(registryHandle!.getPolicy("sidebar").requiresUserGesture).toBe(false);
  });

  it("logs an error and refuses if two A2UISurfaceMounts share the same surfaceId", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    let registryHandle: ReturnType<typeof useSurfaceRegistry> | null = null;
    function Capture() {
      registryHandle = useSurfaceRegistry();
      return null;
    }
    render(
      wrap(
        <>
          <Capture />
          <A2UISurfaceMount surfaceId="workspace" />
          <A2UISurfaceMount surfaceId="workspace" />
        </>,
      ),
    );

    // First mount wins; second logs an error but doesn't crash
    expect(registryHandle!.getMount("workspace")).not.toBeNull();
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
