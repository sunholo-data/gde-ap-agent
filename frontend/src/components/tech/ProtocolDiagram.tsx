/**
 * Four-layer protocol stack diagram for /tech.
 *
 * Mirrors CLAUDE.md lines 28-35 — Layer 4 (UI) on top, Layer 1 (framework)
 * on the bottom. Pure CSS grid + hairlines, no SVG. Each layer shows the
 * protocols it owns and a one-line "what it does in this demo" caption.
 */
const LAYERS: { num: string; name: string; protocols: string[]; role: string }[] = [
  {
    num: "L4",
    name: "UI",
    protocols: ["A2UI", "MCP Apps"],
    role: "Declarative agent UI surfaces + sandboxed iframe artifacts (Vendor Globe, AP Analytics)",
  },
  {
    num: "L3",
    name: "Transport",
    protocols: ["AG-UI"],
    // We integrate AG-UI via @ag-ui/client directly (not via CopilotKit) —
    // CopilotKit's runtimeUrl wants a GraphQL CopilotKit-Runtime endpoint,
    // not a bare AG-UI SSE stream. See AGUIProvider.tsx for the why.
    role: "SSE streaming — every tool call, stage progress event, and emit_* payload reaches the client live via @ag-ui/client",
  },
  {
    num: "L2",
    name: "Coordination",
    protocols: ["A2A", "MCP"],
    role: "Cross-agent discovery via /.well-known/agent.json + tool calls into external MCP servers",
  },
  {
    num: "L1",
    name: "Framework",
    protocols: ["Google ADK"],
    role: "SequentialAgent orchestration, session/memory services, deterministic sub-agent dispatch",
  },
];

export function ProtocolDiagram() {
  return (
    <div className="space-y-px overflow-hidden rounded-lg border border-border bg-border">
      {LAYERS.map((layer) => (
        <div
          key={layer.num}
          className="grid grid-cols-[auto_1fr] gap-x-6 bg-background p-5 md:grid-cols-[auto_auto_1fr] md:p-6"
        >
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-[10px] font-bold tabular-nums text-primary">
              {layer.num}
            </span>
            <span className="font-display text-sm font-semibold uppercase tracking-wider text-foreground">
              {layer.name}
            </span>
          </div>
          <div className="col-span-2 mt-2 flex flex-wrap gap-1.5 md:col-span-1 md:mt-0">
            {layer.protocols.map((p) => (
              <span
                key={p}
                className="rounded-sm border border-primary/25 bg-primary/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-primary"
              >
                {p}
              </span>
            ))}
          </div>
          <p className="col-span-2 mt-2 text-sm leading-relaxed text-muted-foreground md:col-span-1 md:mt-0">
            {layer.role}
          </p>
        </div>
      ))}
    </div>
  );
}
