"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { fetchWithAuth } from "@/lib/apiClient";
import { readLastOutput } from "@/hooks/useSpecialistInvocations";
import type { SpecialistKey } from "@/lib/auditViewFlag";
import { DocparsePicker } from "./forms/DocparsePicker";
import { ValidatorJsonForm } from "./forms/ValidatorJsonForm";
import { PosterVerdictForm } from "./forms/PosterVerdictForm";
import { findSkillByMetaKey } from "@/lib/skillMeta";
import type { Skill } from "@/types/skill";

interface RunStandaloneSectionProps {
  specialistKey: SpecialistKey;
  sessionId: string | null;
  /** All skills available to the user — used to look up the specialist's
   * actual skillId for the API call. */
  skills: Skill[];
  uid: string;
}

interface StandaloneResult {
  duration_ms: number;
  text: string;
  tool_calls: Array<{ name: string; args?: string; result?: unknown }>;
}

export function RunStandaloneSection({
  specialistKey,
  sessionId,
  skills,
  uid,
}: RunStandaloneSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<StandaloneResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const metaKey =
    specialistKey === "docparse" ? "docparse" :
    specialistKey === "validator" ? "validator" : "poster";
  const skill = findSkillByMetaKey(skills, metaKey);
  const skillId = skill?.skillId;

  async function handleSubmit(input: unknown) {
    if (!skillId) {
      setError(`Skill not enrolled: ${specialistKey}`);
      return;
    }
    setError(null);
    setSubmitting(true);
    setResult(null);
    try {
      const res = await fetchWithAuth(
        `/api/proxy/api/skill/${encodeURIComponent(skillId)}/structured`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input, sessionId }),
        },
      );
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          if (body.detail?.errors?.length) {
            detail = `${body.detail.message ?? "Validation failed"}\n• ${body.detail.errors.join("\n• ")}`;
          } else if (body.detail?.message) {
            detail = body.detail.message;
          } else if (typeof body.detail === "string") {
            detail = body.detail;
          }
        } catch { /* ignore */ }
        throw new Error(detail);
      }
      const data = (await res.json()) as StandaloneResult;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between rounded-md border border-border bg-background px-3 py-1.5 text-left text-xs font-semibold transition-colors",
          expanded ? "border-primary/40 text-primary" : "text-foreground hover:border-primary/30",
        )}
      >
        <span className="flex items-center gap-1.5">
          <span className="text-[10px]">⚠</span>
          Run Standalone
        </span>
        <span className="text-muted-foreground">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
          <p className="text-[10px] leading-relaxed text-muted-foreground/70">
            This specialist expects pre-processed input from the orchestrator. Standalone runs are
            for auditing and demos — results may be lower quality outside the pipeline.
          </p>

          {specialistKey === "docparse" && (
            <DocparsePicker
              uid={uid}
              disabled={submitting}
              onSubmit={(input) => void handleSubmit(input)}
            />
          )}
          {specialistKey === "validator" && (
            <ValidatorJsonForm
              defaultValue={readLastOutput(sessionId, "docparse")}
              disabled={submitting}
              onSubmit={(input) => void handleSubmit(input)}
            />
          )}
          {specialistKey === "poster" && (
            <PosterVerdictForm
              defaultValue={readLastOutput(sessionId, "validator")}
              disabled={submitting}
              onSubmit={(input) => void handleSubmit(input)}
            />
          )}

          {submitting && (
            <p className="text-[11px] italic text-primary">Running…</p>
          )}
          {error && (
            <pre className="overflow-auto whitespace-pre-wrap rounded border border-destructive/30 bg-destructive/5 p-2 text-[11px] text-destructive">
              {error}
            </pre>
          )}
          {result && (
            <StandaloneResultView result={result} />
          )}
        </div>
      )}
    </div>
  );
}

function StandaloneResultView({ result }: { result: StandaloneResult }) {
  return (
    <div className="space-y-2 rounded border border-primary/20 bg-primary/5 p-2">
      <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-primary/70">
        <span>Standalone result</span>
        <span>{result.duration_ms}ms · {result.tool_calls.length} tool call{result.tool_calls.length === 1 ? "" : "s"}</span>
      </div>
      {result.text && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-background p-2 text-[11px] leading-relaxed text-foreground/90">
          {result.text}
        </pre>
      )}
      {result.tool_calls.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tool calls ({result.tool_calls.length})
          </summary>
          <ul className="mt-1 space-y-1">
            {result.tool_calls.map((tc, i) => (
              <li key={i} className="rounded bg-background p-1.5 text-[10px] font-mono text-foreground/80">
                <span className="text-primary">{tc.name}</span>
                {tc.args && <span className="ml-1 text-muted-foreground">({truncate(tc.args, 80)})</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
