import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { APPipelineSteps } from "../APPipelineSteps";
import type { ToolCallState } from "@/hooks/useSkillAgent";

function tc(name: string, status: ToolCallState["status"] = "success"): ToolCallState {
  return { id: name, name, status };
}

describe("APPipelineSteps", () => {
  it("renders all 4 step labels", () => {
    render(<APPipelineSteps toolCalls={[]} />);
    expect(screen.getByText("Intake")).toBeInTheDocument();
    expect(screen.getByText("Extract")).toBeInTheDocument();
    expect(screen.getByText("Validate")).toBeInTheDocument();
    expect(screen.getByText("Post")).toBeInTheDocument();
  });

  it("shows Intake as active when no tool calls and isStreaming=true", () => {
    const { container } = render(<APPipelineSteps toolCalls={[]} isStreaming />);
    // Pulsing dot = animate-ping class present
    expect(container.querySelector(".animate-ping")).toBeTruthy();
  });

  it("advances to Extract when transfer_to_docparse fires", () => {
    const { container } = render(
      <APPipelineSteps toolCalls={[tc("transfer_to_docparse")]} />,
    );
    // 2 done dots (Intake + Extract) = 2 filled circles (bg-primary, no animate-ping)
    const doneDots = container.querySelectorAll(".bg-primary:not(.animate-ping)");
    // Extract step done: its dot is bg-primary; check at least 1 label text is primary-coloured
    expect(screen.getByText("Extract").className).toContain("text-primary");
  });

  it("advances to Validate when ap_validator fires", () => {
    render(
      <APPipelineSteps
        toolCalls={[tc("transfer_to_docparse"), tc("transfer_to_ap_validator")]}
      />,
    );
    expect(screen.getByText("Validate").className).toContain("text-primary");
  });

  it("advances to Post when ap_poster fires", () => {
    render(
      <APPipelineSteps
        toolCalls={[
          tc("transfer_to_docparse"),
          tc("transfer_to_ap_validator"),
          tc("transfer_to_ap_poster"),
        ]}
      />,
    );
    expect(screen.getByText("Post").className).toContain("text-primary");
  });

  it("shows pulsing dot when a step tool call is still running", () => {
    const { container } = render(
      <APPipelineSteps
        toolCalls={[tc("transfer_to_docparse", "running")]}
      />,
    );
    expect(container.querySelector(".animate-ping")).toBeTruthy();
  });

  it("has accessible list role", () => {
    render(<APPipelineSteps toolCalls={[]} />);
    expect(screen.getByRole("list", { name: /ap pipeline/i })).toBeInTheDocument();
  });
});
