"use client";

import { useState, useEffect } from "react";

// Strip scripts, external references, and event handlers from agent-generated SVG.
// Config is a named constant so security audits can find and review it in one place.
const PURIFY_CONFIG = {
  USE_PROFILES: { svg: true, svgFilters: true },
  FORBID_TAGS: ["script", "use"],
  // Prevent SSRF via SVG external references
  FORBID_ATTR: ["xlink:href", "href"],
};

interface SVGBlockProps {
  svgString: string;
}

interface CodeFallbackProps {
  code: string;
}

function CodeFallback({ code }: CodeFallbackProps) {
  return (
    <pre className="mb-2 overflow-x-auto rounded border border-border bg-muted p-3 text-xs">
      <code>{code}</code>
    </pre>
  );
}

export function SVGBlock({ svgString }: SVGBlockProps) {
  // Empty string initial state: server renders nothing (no hydration mismatch).
  // useEffect + dynamic import: DOMPurify only runs in the browser where DOM is available.
  const [cleanSvg, setCleanSvg] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    import("dompurify").then(({ default: DOMPurify }) => {
      const clean = DOMPurify.sanitize(svgString, PURIFY_CONFIG) as string;
      if (!clean) {
        setFailed(true);
      } else {
        setCleanSvg(clean);
      }
    });
  }, [svgString]);

  if (failed) return <CodeFallback code={svgString} />;
  if (!cleanSvg) return null;

  return (
    <div
      className="svg-container my-4 max-w-full overflow-x-auto rounded border border-border p-2"
      dangerouslySetInnerHTML={{ __html: cleanSvg }}
    />
  );
}
