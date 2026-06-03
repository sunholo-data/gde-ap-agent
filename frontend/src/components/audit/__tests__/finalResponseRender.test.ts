import { describe, expect, it } from "vitest";
import {
  stripJsonFence,
  tryBuildFinalResponseCard,
} from "../finalResponseRender";

describe("stripJsonFence", () => {
  it("removes ```json fences", () => {
    expect(stripJsonFence('```json\n{"a":1}\n```')).toBe('{"a":1}');
  });

  it("removes bare ``` fences", () => {
    expect(stripJsonFence('```\n{"a":1}\n```')).toBe('{"a":1}');
  });

  it("leaves unfenced text untouched (trimmed)", () => {
    expect(stripJsonFence('  {"a":1}  ')).toBe('{"a":1}');
  });

  it("leaves prose untouched", () => {
    expect(stripJsonFence("Hello world")).toBe("Hello world");
  });
});

describe("tryBuildFinalResponseCard", () => {
  it("returns a v0.9 message array for fenced JSON", () => {
    const out = tryBuildFinalResponseCard(
      '```json\n{"vendor_name":"Acme","total":100}\n```',
      "invoice-extractor",
    );
    expect(out).not.toBeNull();
    expect(out).toHaveLength(3);
    expect(out![0]).toHaveProperty("createSurface");
  });

  it("returns a v0.9 message array for bare JSON", () => {
    const out = tryBuildFinalResponseCard('{"a":1}', "x");
    expect(out).not.toBeNull();
    expect(out).toHaveLength(3);
  });

  it("returns null for prose text", () => {
    expect(tryBuildFinalResponseCard("Hello there.", "x")).toBeNull();
  });

  it("returns null for a malformed JSON-ish payload", () => {
    expect(
      tryBuildFinalResponseCard('```json\n{"a":\n```', "x"),
    ).toBeNull();
  });

  it("uses fallbackTitle as the createSurface namespace", () => {
    const out = tryBuildFinalResponseCard('{"a":1}', "x");
    const cs = (out![0] as { createSurface: { surfaceId: string } })
      .createSurface;
    expect(cs.surfaceId).toBe("audit-final");
  });
});
