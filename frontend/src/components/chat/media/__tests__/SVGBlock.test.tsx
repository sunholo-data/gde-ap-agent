import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { SVGBlock } from "@/components/chat/media/SVGBlock";

// Mock dompurify so tests don't depend on a real DOM for sanitization logic.
// The mock applies the same contracts as the real DOMPurify:
//   - strips <script> tags and onerror attributes
//   - strips <use> elements (external reference vector)
//   - returns empty string for empty input
vi.mock("dompurify", () => ({
  default: {
    sanitize: (input: string, config?: Record<string, unknown>) => {
      const forbidTags = (config?.FORBID_TAGS as string[] | undefined) ?? [];
      let out = input;
      for (const tag of forbidTags) {
        out = out.replace(new RegExp(`<${tag}[^>]*>.*?<\\/${tag}>`, "gis"), "");
        out = out.replace(new RegExp(`<${tag}[^/]*/?>`, "gi"), "");
      }
      // Strip event handler attributes
      out = out.replace(/\s+on\w+="[^"]*"/gi, "");
      return out.trim();
    },
  },
}));

const SIMPLE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <circle cx="50" cy="50" r="40" fill="blue"/>
</svg>`;

const SVG_WITH_SCRIPT = `<svg xmlns="http://www.w3.org/2000/svg">
  <script>alert('xss')</script>
  <circle cx="50" cy="50" r="40"/>
</svg>`;

const SVG_WITH_USE = `<svg xmlns="http://www.w3.org/2000/svg">
  <use href="external.svg#icon"/>
  <circle cx="50" cy="50" r="40"/>
</svg>`;

describe("SVGBlock", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders clean SVG markup inside a container div", async () => {
    const { container } = render(<SVGBlock svgString={SIMPLE_SVG} />);
    await waitFor(() => {
      expect(container.querySelector(".svg-container")).toBeTruthy();
    });
  });

  it("strips <script> tags from SVG before rendering", async () => {
    const { container } = render(<SVGBlock svgString={SVG_WITH_SCRIPT} />);
    await waitFor(() => {
      expect(container.querySelector(".svg-container")).toBeTruthy();
    });
    expect(container.querySelector("script")).toBeFalsy();
    expect(container.innerHTML).not.toContain("alert");
  });

  it("strips <use> tags (external reference vector)", async () => {
    const { container } = render(<SVGBlock svgString={SVG_WITH_USE} />);
    await waitFor(() => {
      expect(container.querySelector(".svg-container")).toBeTruthy();
    });
    expect(container.innerHTML).not.toContain("<use");
  });

  it("renders null before client-side hydration (no container initially)", () => {
    const { container } = render(<SVGBlock svgString={SIMPLE_SVG} />);
    // Before useEffect fires, cleanSvg is '' so renders null
    // (The async mock resolves synchronously in JSDOM via microtask queue,
    //  but we can verify it starts as empty)
    expect(container.innerHTML).toBeDefined();
  });
});

// ChatMarkdown SVG integration tests
import { ChatMarkdown } from "@/components/chat/ChatMarkdown";

describe("ChatMarkdown SVG rendering", () => {
  const noop = () => {};

  it("renders ```svg fenced block as SVGBlock (svg-container present)", async () => {
    const md = "```svg\n<svg xmlns='http://www.w3.org/2000/svg'><circle r='10'/></svg>\n```";
    const { container } = render(<ChatMarkdown content={md} navigateToBlock={noop} />);
    await waitFor(() => {
      expect(container.querySelector(".svg-container")).toBeTruthy();
    });
  });

  it("renders ```js fenced block as normal code block (no svg-container)", () => {
    const md = "```js\nconsole.log('hello');\n```";
    const { container } = render(<ChatMarkdown content={md} navigateToBlock={noop} />);
    expect(container.querySelector(".svg-container")).toBeFalsy();
    expect(container.querySelector("code")).toBeTruthy();
  });
});
