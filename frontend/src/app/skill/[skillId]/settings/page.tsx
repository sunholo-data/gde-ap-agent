"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import ModelSelector from "@/components/skill/ModelSelector";
import { useSkillMeta } from "@/hooks/useSkillMeta";

export default function SkillSettingsPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const { ownerId, slug } = useSkillMeta(skillId);
  // Holds the api_name (e.g. "claude-sonnet-4-6") — what gets stored on the skill doc.
  const [modelApiName, setModelApiName] = useState<string | null>(null);

  const friendlyPath = ownerId && slug ? `/chat/@${ownerId}/${slug}` : null;

  return (
    <main className="p-6 max-w-lg">
      <h1 className="text-xl font-semibold mb-4">Skill Settings</h1>
      <p className="text-sm text-gray-500 mb-1">Skill: {skillId}</p>

      <label className="block mt-4 mb-1 text-sm font-medium" htmlFor="skill-url">
        Public URL
      </label>
      {friendlyPath ? (
        <code
          id="skill-url"
          className="block rounded border border-input bg-muted/50 px-2 py-1 text-xs"
        >
          {friendlyPath}
        </code>
      ) : (
        <p id="skill-url" className="text-xs text-gray-400">
          Loading…
        </p>
      )}

      <label className="block mt-4 mb-1 text-sm font-medium" htmlFor="model-select">
        Model
      </label>
      <ModelSelector
        value={modelApiName}
        onChange={setModelApiName}
      />
      {modelApiName && (
        <p className="mt-2 text-xs text-gray-400">Selected: {modelApiName}</p>
      )}
    </main>
  );
}
