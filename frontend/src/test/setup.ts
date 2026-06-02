import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom doesn't implement ResizeObserver — provide a no-op stub so components
// that use it don't crash in tests. The actual scroll behaviour is a browser
// layout concern and is not meaningful to assert in unit tests.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// vitest's forks pool passes `--localstorage-file` without a valid path,
// which disables jsdom's native localStorage. Provide a minimal stub so
// any component reading localStorage on mount (ThemeToggle, GCSBucketInput,
// audit-view persistence) doesn't crash in tests. Per-test files may
// override with their own stub when they need to assert on writes.
const _lsStore: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (k: string) => _lsStore[k] ?? null,
  setItem: (k: string, v: string) => { _lsStore[k] = v; },
  removeItem: (k: string) => { delete _lsStore[k]; },
  clear: () => { Object.keys(_lsStore).forEach((k) => delete _lsStore[k]); },
  key: (i: number) => Object.keys(_lsStore)[i] ?? null,
  get length() { return Object.keys(_lsStore).length; },
});

// vitest.config singleFork=true under CI runs every test file in the same
// process; without an explicit cleanup, prior renders leak and
// getByTestId() finds multiple nodes. Local (non-CI) pool=forks masks
// this by giving each file its own jsdom. Register cleanup globally so
// both modes behave identically.
afterEach(() => {
  cleanup();
});
