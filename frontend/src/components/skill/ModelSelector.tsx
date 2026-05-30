"use client";

import { useEffect, useState } from "react";

interface ModelEntry {
  id: string;
  api_name: string;
  provider: "google" | "anthropic" | "openai";
  tier: "default" | "smart" | "fast";
  context_window: number;
  max_output_tokens: number;
  description: string;
}

interface ModelsResponse {
  models: ModelEntry[];
  defaults: Record<string, string>;
  platform_default: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google Gemini",
  anthropic: "Anthropic Claude",
  openai: "OpenAI",
};

interface Props {
  value: string | null;
  onChange: (apiName: string) => void;
}

export default function ModelSelector({ value, onChange }: Props) {
  const [config, setConfig] = useState<ModelsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/proxy/api/models")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<ModelsResponse>;
      })
      .then(setConfig)
      .catch(() => setError("Failed to load models"));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!config) return <select disabled aria-label="Loading models…" />;

  const platformDefault = config.models.find(
    (m) => m.id === config.platform_default
  )?.api_name;

  const byProvider = (["google", "anthropic", "openai"] as const).map(
    (provider) => ({
      provider,
      label: PROVIDER_LABELS[provider],
      models: config.models.filter((m) => m.provider === provider),
    })
  );

  return (
    <select
      value={value ?? platformDefault ?? ""}
      onChange={(e) => onChange(e.target.value)}
    >
      {byProvider.map(({ provider, label, models }) => (
        <optgroup key={provider} label={label}>
          {models.map((m) => (
            <option key={m.id} value={m.api_name} title={m.description}>
              {m.description}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
