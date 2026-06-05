/**
 * Four-layer protocol stack diagram for /tech.
 *
 * Mirrors CLAUDE.md lines 28-35 — Layer 4 (UI) on top, Layer 1 (framework)
 * on the bottom. Pure CSS grid + hairlines, no SVG. Each layer shows the
 * protocols it owns and a one-line "what it does in this demo" caption.
 *
 * The top row (`external: true`) sits visually *above* the stack and
 * names systems that *consume* the stack from outside — today that's
 * Gemini Enterprise via the L2 A2A card. Rendered with a dashed border
 * and faded background so it reads as "outside the box" rather than as
 * another layer in the box.
 */
interface Layer {
  num: string;
  name: string;
  protocols: string[];
  role: string;
  external?: boolean;
}

const LAYERS: Layer[] = [
  {
    num: "EXT",
    name: "External consumer",
    protocols: ["Gemini Enterprise"],
    role: "Hypothetical: discovers ap-orchestrator via the L2 A2A card, registers it as a managed agent, renders the L4 A2UI Cards in its own chat surface — no code changes on this side",
    external: true,
  },
  {
    num: "L4",
    name: "UI",
    // MCP Apps is the iframe-sandboxed UI-artifacts spec from the MCP
    // family — distinct from MCP-the-tool-protocol despite the shared
    // family name. We list it here (the UI layer where it belongs) and
    // intentionally do NOT also list bare "MCP" at L2 because this
    // submission ships no live MCP-tool-server integration. See the
    // L2 note below and SUBMISSION.md §"MCP Usage" lines 90-99.
    protocols: ["A2UI", "MCP Apps"],
    role: "Declarative agent UI surfaces (A2UI) + sandboxed iframe artifacts (MCP Apps — Vendor Globe, AP Analytics)",
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
    // Bare "MCP" (the tool-server protocol) is deliberately NOT listed
    // here. The current submission has no active MCP-tool integration
    // — backend/tools/* are plain ADK FunctionTools, not MCP clients,
    // and the ext-ap-erp MCP server block in ap-poster/SKILL.md is
    // commented out as Phase 2 (see SUBMISSION.md). Adding "MCP" here
    // would conflate it with MCP Apps at L4, which is the *UI*
    // artifact spec — a different surface from the same family.
    protocols: ["A2A"],
    role: "Cross-agent discovery via /.well-known/agent.json — registerable with Gemini Enterprise as a managed agent without code changes",
  },
  {
    num: "L1",
    name: "Framework",
    protocols: ["Google ADK"],
    role: "SequentialAgent orchestration, session/memory services, deterministic sub-agent dispatch",
  },
];

export function ProtocolDiagram() {
  // Split so the external-consumer row gets its own visually-detached
  // container with a dashed border — reads as "outside the stack" rather
  // than another layer inside it. Stack layers (L1-L4) live in the
  // hairline-rounded box; the consumer row sits above with its own
  // border + a small gap.
  const stackLayers = LAYERS.filter((l) => !l.external);
  const externalLayers = LAYERS.filter((l) => l.external);

  return (
    <div className="space-y-3">
      {externalLayers.map((layer) => (
        <div
          key={layer.num}
          className="rounded-lg border border-dashed border-primary/40 bg-primary/[0.03] p-5 md:p-6"
        >
          <LayerContent layer={layer} />
        </div>
      ))}
      <div className="space-y-px overflow-hidden rounded-lg border border-border bg-border">
        {stackLayers.map((layer) => (
          <div
            key={layer.num}
            className="grid grid-cols-[auto_1fr] gap-x-6 bg-background p-5 md:grid-cols-[auto_auto_1fr] md:p-6"
          >
            <LayerContent layer={layer} />
          </div>
        ))}
      </div>
    </div>
  );
}

function LayerContent({ layer }: { layer: Layer }) {
  // Used by both the stack-layer rows and the external-consumer row so
  // the chips + role-line typography stay identical (only the
  // container border/background differs above).
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-6 md:grid-cols-[auto_auto_1fr]">
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
  );
}
