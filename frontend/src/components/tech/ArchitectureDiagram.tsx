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
 * - Animation: `stroke-dasharray: 6 6` + `stroke-dashoffset` keyframe
 *   creates the "ant trail" effect. Per-edge `animation-delay` so the
 *   eye follows order.
 * - currentColor everywhere — colours come from Tailwind classes via
 *   the wrapping divs so the diagram inverts cleanly between light and
 *   dark mode without any media-query work.
 * - Labels render in a SEPARATE top layer with a white pill background
 *   so they read legibly on top of edges + grid backdrop. They sit at
 *   ~33% along the edge from the source (not 50%) so they fall in the
 *   typically-less-crowded source half of the path.
 */

import { BRANDING } from "@/lib/branding";

interface NodeSpec {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  sub: string;
  /** Optional small logo rendered at the top-right of the node — used
   * for AILANG to make the "powered by" relationship visible. */
  logoSrc?: string;
}

interface EdgeSpec {
  id: string;
  from: string;
  to: string;
  /** Optional explicit path string. When absent we draw a straight line
   * with one elbow between the right/left edges of the two boxes. */
  d?: string;
  label: string;
  /** ms delay applied to the dash animation so eye-flow follows order. */
  delay: number;
  /** Edge colour — primary (blue, AG-UI/A2UI traffic), ailang (red,
   * AILANG + MCP Apps), muted (grey, ADK runtime + A2A). */
  tone: "primary" | "ailang" | "muted";
  /** Optional override for label position along the path (0…1).
   * Default 0.33 — closer to source where space is usually open. */
  labelT?: number;
  /** Optional fixed label position (SVG units). Overrides labelT. Useful
   * for short edges where neither end has room and the label needs to
   * float above the path in a specific spot. */
  labelXY?: [number, number];
}

// Diagram viewBox: 1200 x 460. CSS scales the whole thing to fit width.
// Wider than the typical 1000 to give the right-side specialists room
// for their edge labels without overlapping the boxes.
const VBW = 1200;
const VBH = 480;

const NODES: NodeSpec[] = [
  { id: "user", x: 20, y: 200, w: 110, h: 60, title: "User", sub: "Browser" },
  { id: "frontend", x: 180, y: 180, w: 170, h: 100, title: "Next.js Frontend", sub: "AG-UI + A2UI client" },
  { id: "fastapi", x: 400, y: 180, w: 170, h: 100, title: "FastAPI", sub: "get_fast_api_app(ADK)" },
  { id: "orchestrator", x: 620, y: 40, w: 170, h: 70, title: "ap-orchestrator", sub: "Gemini 2.5 Pro · LlmAgent" },
  { id: "pipeline", x: 620, y: 180, w: 170, h: 100, title: "ap-pipeline", sub: "ADK SequentialAgent" },
  { id: "extract", x: 900, y: 60, w: 280, h: 70, title: "invoice-extractor", sub: "AILANG Parse · 0 LLM tokens", logoSrc: BRANDING.logo.familyMark },
  { id: "validate", x: 900, y: 165, w: 280, h: 56, title: "ap-validator", sub: "Gemini Flash" },
  { id: "post", x: 900, y: 260, w: 280, h: 56, title: "ap-poster", sub: "Gemini Flash" },
  { id: "mcpapps", x: 180, y: 380, w: 200, h: 70, title: "MCP Sandbox", sub: "Cloud Run · separate origin" },
  { id: "a2a", x: 620, y: 380, w: 200, h: 70, title: "A2A discovery", sub: "/.well-known/agent.json" },
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
    label: "AG-UI SSE",
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
    labelT: 0.5,
  },
  {
    id: "e-pipeline-extract",
    from: "pipeline",
    to: "extract",
    label: "emit_invoice",
    delay: 800,
    tone: "ailang",
    labelXY: [840, 110],
  },
  {
    id: "e-pipeline-validate",
    from: "pipeline",
    to: "validate",
    label: "emit_verdict",
    delay: 1000,
    tone: "primary",
    labelXY: [840, 185],
  },
  {
    id: "e-pipeline-post",
    from: "pipeline",
    to: "post",
    label: "emit_posting",
    delay: 1200,
    tone: "primary",
    labelXY: [840, 280],
  },
  // Return path — A2UI Card payloads stream back to the frontend via the
  // same SSE channel that carried the request. Drawn as a long curving
  // edge under the main flow for visual separation.
  {
    id: "e-back-a2ui",
    from: "pipeline",
    to: "frontend",
    label: "A2UI Cards",
    delay: 1400,
    tone: "primary",
    d: "M 620 270 C 480 340, 380 340, 350 285",
    labelXY: [480, 332],
  },
  {
    id: "e-frontend-mcp",
    from: "frontend",
    to: "mcpapps",
    label: "MCP postMessage",
    delay: 1600,
    tone: "ailang",
    labelT: 0.5,
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

function defaultPath(from: NodeSpec, to: NodeSpec): {
  d: string;
  labelAt: (t: number) => [number, number];
} {
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
  const elbowsHorizontal = Math.abs(a[1] - b[1]) > 10 && Math.abs(a[0] - b[0]) > 40;
  const d = elbowsHorizontal
    ? `M ${a[0]} ${a[1]} L ${mx} ${a[1]} L ${mx} ${b[1]} L ${b[0]} ${b[1]}`
    : `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]}`;
  // For orthogonal elbow paths, sample along the first horizontal
  // segment for early-t and the destination-side horizontal segment for
  // late-t. For straight lines, lerp.
  const labelAt = (t: number): [number, number] => {
    if (elbowsHorizontal) {
      if (t <= 0.5) {
        const tt = t / 0.5;
        return [a[0] + (mx - a[0]) * tt, a[1]];
      }
      const tt = (t - 0.5) / 0.5;
      return [mx + (b[0] - mx) * tt, b[1]];
    }
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  };
  return { d, labelAt };
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
        viewBox={`0 0 ${VBW} ${VBH}`}
        className="relative block h-auto w-full"
        role="img"
        aria-label="Platform architecture: request flows from the browser through Next.js, FastAPI, ADK orchestrator and pipeline, with A2UI Cards and MCP Apps returning to the client."
      >
        <defs>
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

        {/* EDGES — rendered FIRST so nodes overlap them at endpoints. */}
        <g>
          {EDGES.map((edge) => {
            const from = nodeById[edge.from];
            const to = nodeById[edge.to];
            const { d: defaultD } = defaultPath(from, to);
            const d = edge.d ?? defaultD;
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
                    opacity: 0.8,
                  }}
                />
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
              {n.logoSrc && (
                <image
                  href={n.logoSrc}
                  x={n.x + n.w - 28}
                  y={n.y + 8}
                  width="20"
                  height="20"
                  preserveAspectRatio="xMidYMid meet"
                />
              )}
              <text
                x={n.x + n.w / 2}
                y={n.y + 26}
                textAnchor="middle"
                className="fill-foreground font-display"
                style={{ fontSize: "14px", fontWeight: 600 }}
              >
                {n.title}
              </text>
              <text
                x={n.x + n.w / 2}
                y={n.y + 44}
                textAnchor="middle"
                className="fill-muted-foreground font-mono"
                style={{ fontSize: "10px" }}
              >
                {n.sub}
              </text>
            </g>
          ))}
        </g>

        {/* LABELS — rendered LAST, on top of nodes + edges, with a white
            pill background so they read legibly over any underlying
            grid/edge. Uses path-side anchor + perpendicular offset. */}
        <g>
          {EDGES.map((edge) => {
            const from = nodeById[edge.from];
            const to = nodeById[edge.to];
            const { labelAt } = defaultPath(from, to);
            const t = edge.labelT ?? 0.33;
            const pos = edge.labelXY ?? labelAt(t);
            const toneClass =
              edge.tone === "ailang"
                ? "text-ailang"
                : edge.tone === "primary"
                  ? "text-primary"
                  : "text-muted-foreground";
            // Width estimate based on char count — narrow monospace.
            const labelW = Math.max(40, edge.label.length * 6.2 + 14);
            return (
              <g key={`${edge.id}-label`} className={toneClass}>
                <rect
                  x={pos[0] - labelW / 2}
                  y={pos[1] - 9}
                  width={labelW}
                  height="16"
                  rx="3"
                  className="fill-background"
                  stroke="currentColor"
                  strokeWidth="1"
                  strokeOpacity="0.35"
                />
                <text
                  x={pos[0]}
                  y={pos[1] + 3}
                  textAnchor="middle"
                  className="font-mono"
                  style={{ fontSize: "10px", fill: "currentColor", fontWeight: 500 }}
                >
                  {edge.label}
                </text>
              </g>
            );
          })}
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
            className="h-px w-6"
            style={{
              background: `repeating-linear-gradient(90deg, ${
                it.tone === "ailang"
                  ? "hsl(var(--ailang))"
                  : it.tone === "primary"
                    ? "hsl(var(--primary))"
                    : "hsl(var(--muted-foreground))"
              } 0 4px, transparent 4px 8px)`,
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
