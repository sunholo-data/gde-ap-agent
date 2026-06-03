"use client";

// AP pipeline 4-step progress rail.
// Shown on bot messages from the ap-orchestrator skill so judges (and users)
// can see the multi-agent handoff sequence in real time.
//
// Step detection is intentionally loose (substring match) so it survives
// ADK's transfer_to_{name} naming convention regardless of hyphen→underscore
// normalisation.

import type { ToolCallState } from "@/hooks/useSkillAgent";

interface Step {
  label: string;
  /** Substring(s) to match against ToolCallState.name. Used as fallback
   * when no STAGE_PROGRESS events have arrived (e.g. older skills that
   * still exposed sub-agents as transfer_to_agent calls). */
  triggers: string[];
  /** STAGE_PROGRESS stage name emitted by the backend
   * (observability/timing.py + adk/agent.py::_AP_SPECIALIST_STAGE_LABELS).
   * Preferred over tool-name detection since the M1 SequentialAgent
   * refactor — the orchestrator only calls transfer_to_agent(ap-pipeline)
   * once, so sub-agent tool-name substring matching never advances past
   * Intake. */
  stage?: string;
}

const STEPS: Step[] = [
  { label: "Intake", triggers: [] }, // Step 1: always starts active
  // Extract: accept both the new "invoice-extractor" name and the
  // legacy "docparse" name so in-flight sessions or older event streams
  // still light up the right step.
  {
    label: "Extract",
    triggers: ["invoice_extractor", "invoice-extractor", "docparse"],
    stage: "ap_stage_extract",
  },
  {
    label: "Validate",
    triggers: ["ap_validator", "ap-validator", "validator"],
    stage: "ap_stage_validate",
  },
  {
    label: "Post",
    triggers: ["ap_poster", "ap-poster", "poster", "route_to_human"],
    stage: "ap_stage_post",
  },
];

const PIPELINE_DONE_STAGE = "pipeline_done";

type StepStatus = "pending" | "active" | "done";

function resolveStepStatuses(
  toolCalls: ToolCallState[],
  firedStages: ReadonlySet<string> | undefined,
  isStreaming?: boolean,
): StepStatus[] {
  // Find the furthest pipeline step that has fired. STAGE_PROGRESS events
  // are the primary signal (post-M1 SequentialAgent path); tool-name
  // matching is the fallback for older skills and in-flight sessions
  // started before this refactor.
  let furthestTriggered = -1; // -1 = no sub-agent fired yet
  const stagesFired = firedStages ?? new Set<string>();
  const pipelineDone = stagesFired.has(PIPELINE_DONE_STAGE);
  for (let i = 1; i < STEPS.length; i++) {
    const stage = STEPS[i].stage;
    const stageFired = stage !== undefined && stagesFired.has(stage);
    const toolFired = toolCalls.some((tc) =>
      STEPS[i].triggers.some((t) => tc.name.toLowerCase().includes(t)),
    );
    if (stageFired || toolFired) furthestTriggered = i;
  }

  return STEPS.map((_, i): StepStatus => {
    if (furthestTriggered === -1) {
      // No sub-agents fired yet: Intake is active while streaming, done when complete.
      if (i === 0) return isStreaming ? "active" : "done";
      return "pending";
    }
    if (i < furthestTriggered) return "done";
    if (i === furthestTriggered) {
      // Pipeline emits ``pipeline_done`` after the final stage's
      // after_agent_callback. Once seen, every fired stage is done —
      // STAGE_PROGRESS has no "stage_finished" counterpart so we infer
      // completion from the closing event.
      if (pipelineDone) return "done";
      const stage = STEPS[i].stage;
      const stageActive = stage !== undefined && stagesFired.has(stage);
      const toolRunning = toolCalls.some(
        (tc) =>
          tc.status === "running" &&
          STEPS[i].triggers.some((t) => tc.name.toLowerCase().includes(t)),
      );
      // When stage fired and we're still streaming, the stage is in
      // progress. When the run has finished, treat the last fired stage
      // as done (no further STAGE_PROGRESS events will arrive).
      if (toolRunning) return "active";
      if (stageActive && isStreaming) return "active";
      return "done";
    }
    return "pending";
  });
}

interface APPipelineStepsProps {
  toolCalls: ToolCallState[];
  /** Set of STAGE_PROGRESS stage names that have fired during the current
   * run (e.g. ``"ap_stage_extract"``). Preferred over tool-name matching
   * since the M1 SequentialAgent refactor — sub-agent invocations no
   * longer surface as transfer_to_agent tool calls. */
  firedStages?: ReadonlySet<string>;
  /** Whether the agent turn is still streaming. Step 1 shows as active while true. */
  isStreaming?: boolean;
}

export function APPipelineSteps({ toolCalls, firedStages, isStreaming }: APPipelineStepsProps) {
  const finalStatuses = resolveStepStatuses(toolCalls, firedStages, isStreaming);

  return (
    <div className="mb-2 flex items-center gap-0" role="list" aria-label="AP pipeline progress">
      {STEPS.map((step, i) => (
        <StepItem
          key={step.label}
          label={step.label}
          status={finalStatuses[i]}
          isLast={i === STEPS.length - 1}
        />
      ))}
    </div>
  );
}

interface StepItemProps {
  label: string;
  status: StepStatus;
  isLast: boolean;
}

function StepItem({ label, status, isLast }: StepItemProps) {
  return (
    <div className="flex items-center" role="listitem">
      <div className="flex flex-col items-center gap-0.5">
        <Dot status={status} />
        <span
          className={[
            "text-[10px] font-medium leading-none",
            status === "done"
              ? "text-primary"
              : status === "active"
                ? "text-primary"
                : "text-muted-foreground/50",
          ].join(" ")}
        >
          {label}
        </span>
      </div>
      {!isLast && (
        <div
          className={[
            "mx-1 mb-3 h-px w-8 shrink-0",
            status === "done" ? "bg-primary/60" : "bg-border",
          ].join(" ")}
          aria-hidden="true"
        />
      )}
    </div>
  );
}

function Dot({ status }: { status: StepStatus }) {
  if (status === "done") {
    return (
      <div className="flex h-4 w-4 items-center justify-center rounded-full bg-primary">
        <svg className="h-2.5 w-2.5" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2" aria-label="Done">
          <path d="M2 5l2.5 2.5L8 2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    );
  }
  if (status === "active") {
    return (
      <div className="relative flex h-4 w-4 items-center justify-center">
        <div className="absolute h-4 w-4 animate-ping rounded-full bg-primary/30" />
        <div className="h-2.5 w-2.5 rounded-full bg-primary" />
      </div>
    );
  }
  // pending
  return <div className="h-4 w-4 rounded-full border-2 border-border bg-background" />;
}
