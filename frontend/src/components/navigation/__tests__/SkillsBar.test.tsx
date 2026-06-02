import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SkillsBar } from "../SkillsBar";
import type { Skill } from "@/types/skill";

function makeSkill(overrides: Partial<Skill> = {}): Skill {
  return {
    name: "research",
    description: "",
    instructions: "",
    skillMetadata: {
      author: "test",
      version: "1.0",
      model: "gemini-2.5-flash",
      tools: [],
      toolConfigs: {},
      subSkills: [],
    },
    references: {},
    assets: {},
    skillId: "skill-1",
    slug: null,
    displayName: "Research",
    avatar: "",
    ownerEmail: "u@example.com",
    ownerId: "uid-1",
    accessControl: { type: "private" },
    protocols: {
      mcp: { enabled: false },
      a2a: { enabled: false },
      agui: { enabled: true },
      a2ui: { enabled: false },
      mcpApps: { enabled: false },
    },
    initialMessage: "",
    tags: [],
    featured: false,
    usageCount: 0,
    createdAt: 0,
    updatedAt: 0,
    ...overrides,
  };
}

describe("SkillsBar", () => {
  it("renders skills as tabs and marks the active one", () => {
    const skills = [
      makeSkill({ skillId: "s1", displayName: "Research" }),
      makeSkill({ skillId: "s2", displayName: "Writer" }),
    ];
    render(<SkillsBar skills={skills} activeSkillId="s2" isLoading={false} onCreateClick={() => {}} />);

    const writer = screen.getByText("Writer").closest("a")!;
    const research = screen.getByText("Research").closest("a")!;
    expect(writer).toHaveAttribute("aria-current", "page");
    expect(research).not.toHaveAttribute("aria-current");
  });

  it("renders skeleton when loading", () => {
    render(<SkillsBar skills={[]} activeSkillId="" isLoading={true} onCreateClick={() => {}} />);
    expect(screen.getByTestId("skill-tabs-skeleton")).toBeInTheDocument();
  });

  it("shows loading copy when user has no skills (post-competition design)", () => {
    // Per the competition design, the Create button + "No skills" empty
    // state were replaced with a passive "Loading skills…" copy — the AP
    // demo has a fixed roster of 4 skills, never an empty marketplace.
    render(<SkillsBar skills={[]} activeSkillId="" isLoading={false} onCreateClick={() => {}} />);
    expect(screen.getByText(/loading skills/i)).toBeInTheDocument();
  });

  it("does not render a create button (hidden per competition design)", () => {
    // onCreateClick is kept on the API surface for upstream parity but
    // the button is hidden in this fork — see SkillsBar.tsx JSDoc.
    const handleCreate = vi.fn();
    render(<SkillsBar skills={[]} activeSkillId="" isLoading={false} onCreateClick={handleCreate} />);
    expect(screen.queryByLabelText(/create a new skill/i)).not.toBeInTheDocument();
    expect(handleCreate).not.toHaveBeenCalled();
  });

  it("uses friendly URL on tab when slug is set, UUID fallback otherwise", () => {
    const skills = [
      makeSkill({ skillId: "uuid-1", slug: "research", ownerId: "mark" }),
      makeSkill({ skillId: "uuid-2", slug: null, displayName: "No-Slug" }),
    ];
    render(<SkillsBar skills={skills} activeSkillId="uuid-1" isLoading={false} onCreateClick={() => {}} />);
    expect(screen.getByText("Research").closest("a")).toHaveAttribute("href", "/chat/@mark/research");
    expect(screen.getByText("No-Slug").closest("a")).toHaveAttribute("href", "/chat/uuid-2");
  });

  // === Audit View (multi-agent-inspector-ux.md) ===

  it("renders Audit View chips when invocations + onChipSelect are provided", () => {
    const invocations = {
      docparse: { current: null, history: [], status: "idle" as const },
      validator: { current: null, history: [], status: "idle" as const },
      poster: { current: null, history: [], status: "idle" as const },
    };
    render(
      <SkillsBar
        skills={[]}
        activeSkillId=""
        isLoading={false}
        onCreateClick={() => {}}
        invocations={invocations}
        openInspectorKey={null}
        onChipSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("audit-view-bar")).toBeInTheDocument();
    expect(screen.getByTestId("audit-chip-docparse")).toBeInTheDocument();
    expect(screen.getByTestId("audit-chip-validator")).toBeInTheDocument();
    expect(screen.getByTestId("audit-chip-poster")).toBeInTheDocument();
  });

  it("does not render Audit View chips when no invocations are passed", () => {
    render(<SkillsBar skills={[]} activeSkillId="" isLoading={false} onCreateClick={() => {}} />);
    expect(screen.queryByTestId("audit-view-bar")).not.toBeInTheDocument();
  });

  it("fires onChipSelect when a specialist chip is clicked", async () => {
    const invocations = {
      docparse: { current: null, history: [], status: "idle" as const },
      validator: { current: null, history: [], status: "idle" as const },
      poster: { current: null, history: [], status: "idle" as const },
    };
    const onChipSelect = vi.fn();
    render(
      <SkillsBar
        skills={[]}
        activeSkillId=""
        isLoading={false}
        onCreateClick={() => {}}
        invocations={invocations}
        openInspectorKey={null}
        onChipSelect={onChipSelect}
      />,
    );
    await userEvent.click(screen.getByTestId("audit-chip-validator"));
    expect(onChipSelect).toHaveBeenCalledWith("validator");
  });
});
