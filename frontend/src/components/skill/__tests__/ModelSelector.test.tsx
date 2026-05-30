import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import ModelSelector from "../ModelSelector";

const MOCK_MODELS_RESPONSE = {
  models: [
    {
      id: "gemini-3-flash",
      api_name: "gemini-3-flash-preview",
      provider: "google",
      tier: "default",
      context_window: 1_000_000,
      max_output_tokens: 65_536,
      description: "Gemini 3 Flash",
    },
    {
      id: "gemini-3-1-pro",
      api_name: "gemini-3.1-pro-preview",
      provider: "google",
      tier: "smart",
      context_window: 1_000_000,
      max_output_tokens: 65_536,
      description: "Gemini 3.1 Pro",
    },
    {
      id: "claude-sonnet-4-6",
      api_name: "claude-sonnet-4-6",
      provider: "anthropic",
      tier: "default",
      context_window: 200_000,
      max_output_tokens: 64_000,
      description: "Claude Sonnet 4.6",
    },
    {
      id: "claude-opus-4-7",
      api_name: "claude-opus-4-7",
      provider: "anthropic",
      tier: "smart",
      context_window: 200_000,
      max_output_tokens: 64_000,
      description: "Claude Opus 4.7",
    },
    {
      id: "gpt-5-4",
      api_name: "gpt-5.4",
      provider: "openai",
      tier: "smart",
      context_window: 1_000_000,
      max_output_tokens: 128_000,
      description: "GPT-5.4",
    },
    {
      id: "gpt-5-1-instant",
      api_name: "gpt-5.1-chat-latest",
      provider: "openai",
      tier: "default",
      context_window: 400_000,
      max_output_tokens: 128_000,
      description: "GPT-5.1 Instant",
    },
  ],
  defaults: {
    google: "gemini-3-flash",
    anthropic: "claude-sonnet-4-6",
    openai: "gpt-5-1-instant",
  },
  platform_default: "gemini-3-flash",
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MOCK_MODELS_RESPONSE),
    })
  );
});

describe("ModelSelector", () => {
  it("renders a loading state then shows options", async () => {
    render(<ModelSelector value={null} onChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });
  });

  it("groups options by provider", async () => {
    render(<ModelSelector value={null} onChange={vi.fn()} />);
    // Wait for an option to appear, not just the loading select.
    await screen.findByRole("option", { name: /gemini 3 flash/i });
    const groups = screen.getAllByRole("group");
    const labels = groups.map((g) => g.getAttribute("label") ?? g.textContent);
    expect(labels.some((l) => l?.toLowerCase().includes("google"))).toBe(true);
    expect(labels.some((l) => l?.toLowerCase().includes("anthropic"))).toBe(true);
    expect(labels.some((l) => l?.toLowerCase().includes("openai"))).toBe(true);
  });

  it("defaults to platform_default when value is null", async () => {
    render(<ModelSelector value={null} onChange={vi.fn()} />);
    // The component renders a loading <select disabled> first (also a
    // combobox role). Wait for an actual option to appear before reading
    // the select value, otherwise we may sample the loading state on a
    // slow CI runner.
    await screen.findByRole("option", { name: /gemini 3 flash/i });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("gemini-3-flash-preview");
  });

  it("reflects a provided value", async () => {
    render(<ModelSelector value="claude-sonnet-4-6" onChange={vi.fn()} />);
    await screen.findByRole("option", { name: /claude sonnet/i });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("claude-sonnet-4-6");
  });

  it("calls onChange with api_name when selection changes", async () => {
    const onChange = vi.fn();
    render(<ModelSelector value={null} onChange={onChange} />);
    await screen.findByRole("option", { name: /claude opus/i });
    await userEvent.selectOptions(
      screen.getByRole("combobox"),
      "claude-opus-4-7"
    );
    expect(onChange).toHaveBeenCalledWith("claude-opus-4-7");
  });

  it("fetches from /api/proxy/api/models", async () => {
    render(<ModelSelector value={null} onChange={vi.fn()} />);
    await screen.findByRole("option", { name: /gemini 3 flash/i });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/proxy/api/models");
  });

  it("shows error message when fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500 })
    );
    render(<ModelSelector value={null} onChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/failed to load models/i)).toBeInTheDocument();
    });
  });
});
