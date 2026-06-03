import { describe, expect, it } from "vitest";
import { formatJsonish } from "../sharedView";

describe("formatJsonish", () => {
  it("returns empty string for null/undefined", () => {
    expect(formatJsonish(null)).toBe("");
    expect(formatJsonish(undefined)).toBe("");
  });

  it("returns empty string for blank string", () => {
    expect(formatJsonish("   ")).toBe("");
  });

  it("pretty-prints a JSON string", () => {
    expect(formatJsonish('{"a":1}')).toBe('{\n  "a": 1\n}');
  });

  it("pretty-prints an already-parsed object", () => {
    expect(formatJsonish({ a: 1 })).toBe('{\n  "a": 1\n}');
  });

  it("returns plain strings as-is (trimmed)", () => {
    expect(formatJsonish("  hello  ")).toBe("hello");
  });

  it("unwraps a nested JSON-string value (send_a2ui_json_to_client input shape)", () => {
    const input = JSON.stringify({ a2ui_json: '[{"version":"v0.9"}]' });
    const out = formatJsonish(input);
    expect(out).toContain('"a2ui_json": [');
    expect(out).toContain('"version": "v0.9"');
    expect(out).not.toContain('\\"');
  });

  it("unwraps recursively but caps depth", () => {
    // 6 levels of nesting — deeper than the depth-4 cap. The helper should
    // succeed without throwing and still produce something sensible.
    let value: unknown = "leaf";
    for (let i = 0; i < 6; i++) {
      value = { wrap: JSON.stringify(value) };
    }
    const out = formatJsonish(value);
    expect(out).toContain('"wrap"');
  });

  it("leaves malformed inner JSON strings alone", () => {
    const input = JSON.stringify({ a2ui_json: "[not valid json" });
    const out = formatJsonish(input);
    expect(out).toContain('"[not valid json"');
  });
});
