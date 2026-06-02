import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TypingIndicator } from "../TypingIndicator";
import { BRANDING } from "@/lib/branding";

describe("TypingIndicator", () => {
  it("renders three animated dots when no tool is active", () => {
    const { container } = render(<TypingIndicator />);
    const dots = container.querySelectorAll(".animate-bounce");
    expect(dots).toHaveLength(3);
  });

  it("renders the bot avatar image with branded alt text", () => {
    render(<TypingIndicator />);
    expect(screen.getByRole("img", { name: BRANDING.appName })).toBeInTheDocument();
  });

  it("shows tool name when activeToolName is provided", () => {
    render(<TypingIndicator activeToolName="web_search" />);
    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(screen.queryAllByRole("presentation").length).toBeGreaterThanOrEqual(0);
  });

  it("hides three dots when activeToolName is provided", () => {
    const { container } = render(<TypingIndicator activeToolName="list_documents" />);
    expect(container.querySelectorAll(".animate-bounce")).toHaveLength(0);
  });

  // ttft-instrumentation.md M2: STAGE_PROGRESS labels surface the
  // backend's per-stage progress (Reading 2 documents…, Thinking…,
  // Calling search…) inside the typing indicator before any model
  // token lands. Decouples perceived TTFT from real model TTFT.
  describe("stageLabel (server-authored stage progress)", () => {
    it("renders stageLabel when provided", () => {
      render(<TypingIndicator stageLabel="Reading 2 documents…" />);
      expect(screen.getByText("Reading 2 documents…")).toBeInTheDocument();
    });

    it("hides three dots when stageLabel is provided", () => {
      const { container } = render(<TypingIndicator stageLabel="Thinking…" />);
      expect(container.querySelectorAll(".animate-bounce")).toHaveLength(0);
    });

    it("stageLabel takes priority over activeToolName", () => {
      // The server-authored label is canonical — if the backend has
      // emitted a STAGE_PROGRESS, that's what the user should see,
      // not the local toolName fallback.
      render(<TypingIndicator stageLabel="Calling web_search…" activeToolName="other_tool" />);
      expect(screen.getByText("Calling web_search…")).toBeInTheDocument();
      expect(screen.queryByText("other_tool")).not.toBeInTheDocument();
    });

    it("falls back to activeToolName when stageLabel is null", () => {
      render(<TypingIndicator stageLabel={null} activeToolName="ai_search" />);
      expect(screen.getByText("ai_search")).toBeInTheDocument();
    });

    it("falls back to dots when both stageLabel and activeToolName are absent", () => {
      const { container } = render(<TypingIndicator stageLabel={null} />);
      expect(container.querySelectorAll(".animate-bounce")).toHaveLength(3);
    });
  });

  // stuck-session debrief 2026-06-02: the inactivity watchdog in
  // useSkillAgent surfaces a stalledMs counter past the soft threshold
  // (default 20s). TypingIndicator renders "Still working… (Xs)" with
  // a visually distinct amber colour so the user knows the agent is
  // taking longer than expected — not that it crashed.
  describe("stalledMs (inactivity watchdog)", () => {
    it("renders 'Still working… (Xs)' when stalledMs is set", () => {
      render(<TypingIndicator stalledMs={22_400} />);
      expect(screen.getByText("Still working… (22s)")).toBeInTheDocument();
    });

    it("stalledMs overrides stageLabel", () => {
      render(<TypingIndicator stageLabel="Thinking…" stalledMs={25_000} />);
      expect(screen.getByText("Still working… (25s)")).toBeInTheDocument();
      expect(screen.queryByText("Thinking…")).not.toBeInTheDocument();
    });

    it("stalledMs overrides activeToolName", () => {
      render(<TypingIndicator activeToolName="ap_validator" stalledMs={30_000} />);
      expect(screen.getByText("Still working… (30s)")).toBeInTheDocument();
      expect(screen.queryByText("ap_validator")).not.toBeInTheDocument();
    });

    it("does not flip into stalled mode when stalledMs is null", () => {
      render(<TypingIndicator stalledMs={null} stageLabel="Reading 1 document…" />);
      expect(screen.queryByText(/still working/i)).not.toBeInTheDocument();
      expect(screen.getByText("Reading 1 document…")).toBeInTheDocument();
    });

    it("uses amber colour when stalled (visual distinction)", () => {
      const { container } = render(<TypingIndicator stalledMs={20_000} />);
      // Amber dot replaces the orange pulse so the user can spot
      // the stalled state at a glance.
      expect(container.querySelector(".bg-yellow-500")).toBeTruthy();
      expect(container.querySelector(".bg-orange-400")).toBeNull();
    });
  });
});
