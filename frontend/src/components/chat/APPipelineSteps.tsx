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
  /** Substring(s) to match against ToolCallState.name */
  triggers: string[];
}

const STEPS: Step[] = [
  { label: "Intake",   triggers: [] },          // Step 1: always starts active
  // Extract: accept both the new "invoice-extractor" name and the
  // legacy "docparse" name so in-flight sessions or older event streams
  // still light up the right step.
  { label: "Extract",  triggers: ["invoice_extractor", "invoice-extractor", "docparse"] },
  { label: "Validate", triggers: ["ap_validator", "ap-validator", "validator"] },
  { label: "Post",     triggers: ["ap_poster", "ap-poster", "poster", "route_to_human"] },
];

type StepStatus = "pending" | "active" | "done";

function resolveStepStatuses(toolCalls: ToolCallState[], isStreaming?: boolean): StepStatus[] {
  // Find the furthest sub-agent step that has fired (steps 1–3; step 0 = Intake has no triggers).
  let furthestTriggered = -1; // -1 = no sub-agent fired yet
  for (let i = 1; i < STEPS.length; i++) {
    const fired = toolCalls.some((tc) =>
      STEPS[i].triggers.some((t) => tc.name.toLowerCase().includes(t)),
    );
    if (fired) furthestTriggered = i;
  }

  return STEPS.map((_, i): StepStatus => {
    if (furthestTriggered === -1) {
      // No sub-agents fired yet: Intake is active while streaming, done when complete.
      if (i === 0) return isStreaming ? "active" : "done";
      return "pending";
    }
    if (i < furthestTriggered) return "done";
    if (i === furthestTriggered) {
      const running = toolCalls.some(
        (tc) =>
          tc.status === "running" &&
          STEPS[i].triggers.some((t) => tc.name.toLowerCase().includes(t)),
      );
      return running ? "active" : "done";
    }
    return "pending";
  });
}

interface APPipelineStepsProps {
  toolCalls: ToolCallState[];
  /** Whether the agent turn is still streaming. Step 1 shows as active while true. */
  isStreaming?: boolean;
}

export function APPipelineSteps({ toolCalls, isStreaming }: APPipelineStepsProps) {
  const finalStatuses = resolveStepStatuses(toolCalls, isStreaming);

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
