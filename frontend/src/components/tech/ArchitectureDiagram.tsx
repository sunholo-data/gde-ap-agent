"use client";

/**
 * Animated architecture diagram for /tech.
 *
 * Shows the full request-to-render path of one invoice through the
 * platform. Each protocol owns a labelled edge between two nodes; the
 * edge stroke is animated (stroke-dashoffset keyframe) so the diagram
 * reads as a live system rather than a static snapshot.
 *
 * Implementation notes:
 * - Pure inline SVG, no D3 / no diagramming library. The shape is fixed
 *   so we can hand-place every label without a layout engine.
 * - Anim: `stroke-dasharray: 6 6` + `stroke-dashoffset` keyframe creates
 *   the "ant trail" effect. Each edge gets its own animation-delay so
 *   the eye follows the flow.
 * - currentColor everywhere — colours come from Tailwind classes via
 *   the wrapping divs so the diagram inverts cleanly between light and
 *   dark mode without any media-query work.
 */

interface NodeSpec {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  sub: string;
}

interface EdgeSpec {
  id: string;
  from: string;
  to: string;
  /** Optional explicit path string. When absent we draw a straight line
   * with one elbow between the centres of the two boxes. */
  d?: string;
  label: string;
  /** ms delay applied to the dash animation so eye-flow follows order. */
  delay: number;
  /** Tints the edge — used to differentiate transport (blue, AG-UI),
   * UI (gold-ish), and coordination (muted). */
  tone: "primary" | "ailang" | "muted";
}

// Diagram viewBox: 1000 x 460. Coordinates are SVG units, not pixels —
// CSS scales the whole thing to fit the container width.
const NODES: NodeSpec[] = [
  { id: "user", x: 20, y: 200, w: 110, h: 60, title: "Judge", sub: "Browser" },
  { id: "frontend", x: 180, y: 180, w: 170, h: 100, title: "Next.js Frontend", sub: "AG-UI + A2UI client" },
  { id: "fastapi", x: 400, y: 180, w: 170, h: 100, title: "FastAPI", sub: "get_fast_api_app(ADK)" },
  { id: "orchestrator", x: 620, y: 50, w: 160, h: 70, title: "ap-orchestrator", sub: "Gemini 2.5 Pro · LlmAgent" },
  { id: "pipeline", x: 620, y: 180, w: 160, h: 100, title: "ap-pipeline", sub: "ADK SequentialAgent" },
  { id: "extract", x: 820, y: 60, w: 160, h: 56, title: "invoice-extractor", sub: "AILANG Parse · 0 LLM tokens" },
  { id: "validate", x: 820, y: 150, w: 160, h: 56, title: "ap-validator", sub: "Gemini Flash" },
  { id: "post", x: 820, y: 240, w: 160, h: 56, title: "ap-poster", sub: "Gemini Flash" },
  { id: "mcpapps", x: 180, y: 360, w: 170, h: 70, title: "MCP Sandbox", sub: "Cloud Run · separate origin" },
  { id: "a2a", x: 620, y: 360, w: 160, h: 70, title: "A2A discovery", sub: "/.well-known/agent.json" },
];

const EDGES: EdgeSpec[] = [
  {
    id: "e-user-frontend",
    from: "user",
    to: "frontend",
    label: "HTTPS",
    delay: 0,
    tone: "muted",
  },
  {
    id: "e-frontend-fastapi",
    from: "frontend",
    to: "fastapi",
    label: "AG-UI · SSE",
    delay: 200,
    tone: "primary",
  },
  {
    id: "e-fastapi-orch",
    from: "fastapi",
    to: "orchestrator",
    label: "ADK Runner",
    delay: 400,
    tone: "muted",
  },
  {
    id: "e-orch-pipeline",
    from: "orchestrator",
    to: "pipeline",
    label: "transfer_to_agent",
    delay: 600,
    tone: "muted",
  },
  {
    id: "e-pipeline-extract",
    from: "pipeline",
    to: "extract",
    label: "emit_invoice_extraction",
    delay: 800,
    tone: "ailang",
  },
  {
    id: "e-pipeline-validate",
    from: "pipeline",
    to: "validate",
    label: "emit_ap_verdict",
    delay: 1000,
    tone: "primary",
  },
  {
    id: "e-pipeline-post",
    from: "pipeline",
    to: "post",
    label: "emit_posting_record",
    delay: 1200,
    tone: "primary",
  },
  // Return path — A2UI Card payloads stream back to the frontend via the
  // same SSE channel that carried the request. Drawn as a long curving
  // edge under the main flow for visual separation.
  {
    id: "e-back-a2ui",
    from: "pipeline",
    to: "frontend",
    label: "A2UI Cards · workspace surface",
    delay: 1400,
    tone: "primary",
    d: "M 620 270 C 500 330, 380 330, 350 260",
  },
  {
    id: "e-frontend-mcp",
    from: "frontend",
    to: "mcpapps",
    label: "MCP Apps · postMessage",
    delay: 1600,
    tone: "ailang",
  },
  {
    id: "e-fastapi-a2a",
    from: "fastapi",
    to: "a2a",
    label: "A2A",
    delay: 1800,
    tone: "muted",
  },
];

function nodeCenter(n: NodeSpec): [number, number] {
  return [n.x + n.w / 2, n.y + n.h / 2];
}

function rightOf(n: NodeSpec): [number, number] {
  return [n.x + n.w, n.y + n.h / 2];
}
function leftOf(n: NodeSpec): [number, number] {
  return [n.x, n.y + n.h / 2];
}
function topOf(n: NodeSpec): [number, number] {
  return [n.x + n.w / 2, n.y];
}
function bottomOf(n: NodeSpec): [number, number] {
  return [n.x + n.w / 2, n.y + n.h];
}

function defaultPath(from: NodeSpec, to: NodeSpec): { d: string; mid: [number, number] } {
  // Prefer right→left horizontal edges when the destination is to the
  // right; vertical when stacked; orthogonal elbow otherwise.
  const [fcx, fcy] = nodeCenter(from);
  const [tcx, tcy] = nodeCenter(to);
  let a: [number, number];
  let b: [number, number];
  if (tcx > fcx + 20) {
    a = rightOf(from);
    b = leftOf(to);
  } else if (tcx < fcx - 20) {
    a = leftOf(from);
    b = rightOf(to);
  } else if (tcy > fcy) {
    a = bottomOf(from);
    b = topOf(to);
  } else {
    a = topOf(from);
    b = bottomOf(to);
  }
  const mx = (a[0] + b[0]) / 2;
  // Orthogonal elbow: from→(mx,fromY)→(mx,toY)→to
  const elbowsHorizontal = Math.abs(a[1] - b[1]) > 10 && Math.abs(a[0] - b[0]) > 40;
  const d = elbowsHorizontal
    ? `M ${a[0]} ${a[1]} L ${mx} ${a[1]} L ${mx} ${b[1]} L ${b[0]} ${b[1]}`
    : `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]}`;
  const mid: [number, number] = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  return { d, mid };
}

export function ArchitectureDiagram() {
  const nodeById = Object.fromEntries(NODES.map((n) => [n.id, n]));

  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-muted/20">
      {/* Faint dot-grid backdrop so the diagram reads as a system canvas. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            "radial-gradient(circle, hsl(var(--primary)) 1px, transparent 1px)",
          backgroundSize: "20px 20px",
        }}
      />

      <svg
        viewBox="0 0 1000 460"
        className="relative block h-auto w-full"
        role="img"
        aria-label="Platform architecture: request flows from the browser through Next.js, FastAPI, ADK orchestrator and pipeline, with A2UI Cards and MCP Apps returning to the client."
      >
        <defs>
          {/* Arrow head used at the destination end of every edge. */}
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L10 5 L0 10 z" fill="currentColor" />
          </marker>
        </defs>

        {/* EDGES — render first so nodes sit on top */}
        <g className="text-muted-foreground">
          {EDGES.map((edge) => {
            const from = nodeById[edge.from];
            const to = nodeById[edge.to];
            const { d: defaultD, mid } = defaultPath(from, to);
            const d = edge.d ?? defaultD;
            // We need a mid-point for the label. For custom paths
            // (with explicit d) we estimate by sampling — for orthogonal
            // we use the elbow midpoint computed above.
            const toneClass =
              edge.tone === "ailang"
                ? "text-ailang"
                : edge.tone === "primary"
                  ? "text-primary"
                  : "text-muted-foreground";
            return (
              <g key={edge.id} className={toneClass}>
                <path
                  d={d}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeDasharray="6 6"
                  markerEnd="url(#arrow)"
                  style={{
                    animation: `arch-dash 1.6s linear infinite`,
                    animationDelay: `${edge.delay}ms`,
                    opacity: 0.85,
                  }}
                />
                <text
                  x={mid[0]}
                  y={mid[1] - 4}
                  textAnchor="middle"
                  className="font-mono"
                  style={{ fontSize: "10px", fill: "currentColor", opacity: 0.7 }}
                >
                  {edge.label}
                </text>
              </g>
            );
          })}
        </g>

        {/* NODES */}
        <g>
          {NODES.map((n) => (
            <g key={n.id}>
              <rect
                x={n.x}
                y={n.y}
                width={n.w}
                height={n.h}
                rx="8"
                className="fill-background stroke-border"
                strokeWidth="1.2"
              />
              <text
                x={n.x + n.w / 2}
                y={n.y + 24}
                textAnchor="middle"
                className="fill-foreground font-display"
                style={{ fontSize: "13px", fontWeight: 600 }}
              >
                {n.title}
              </text>
              <text
                x={n.x + n.w / 2}
                y={n.y + 42}
                textAnchor="middle"
                className="fill-muted-foreground font-mono"
                style={{ fontSize: "10px" }}
              >
                {n.sub}
              </text>
            </g>
          ))}
        </g>
      </svg>

      <Legend />

      <style jsx>{`
        @keyframes arch-dash {
          to {
            stroke-dashoffset: -24;
          }
        }
      `}</style>
    </div>
  );
}

function Legend() {
  const items: { tone: "primary" | "ailang" | "muted"; label: string }[] = [
    { tone: "primary", label: "AG-UI / A2UI traffic" },
    { tone: "ailang", label: "AILANG Parse + MCP Apps" },
    { tone: "muted", label: "ADK runtime + A2A" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border bg-background/60 px-4 py-3 backdrop-blur">
      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
        Legend
      </span>
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-2">
          <span
            className={[
              "h-px w-6",
              it.tone === "ailang"
                ? "bg-ailang"
                : it.tone === "primary"
                  ? "bg-primary"
                  : "bg-muted-foreground/60",
            ].join(" ")}
            style={{
              backgroundImage: `repeating-linear-gradient(90deg, currentColor 0 4px, transparent 4px 8px)`,
              color:
                it.tone === "ailang"
                  ? "hsl(var(--ailang))"
                  : it.tone === "primary"
                    ? "hsl(var(--primary))"
                    : "hsl(var(--muted-foreground))",
              background: "transparent",
            }}
          />
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {it.label}
          </span>
        </span>
      ))}
    </div>
  );
}
