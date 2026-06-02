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
import type { StandaloneResult } from "./StandaloneResultView";

interface RunStandaloneSectionProps {
  specialistKey: SpecialistKey;
  sessionId: string | null;
  /** All skills available to the user — used to look up the specialist's
   * actual skillId for the API call. */
  skills: Skill[];
  uid: string;
  /** Lift the run result up to the panel so the body can render it
   * prominently instead of burying it in this footer. */
  onResult: (result: StandaloneResult) => void;
  /** Local submission/error state lifted too so the panel can show a
   * subtle "running…" indicator near the top while the request is in flight. */
  onSubmittingChange?: (submitting: boolean) => void;
}

export function RunStandaloneSection({
  specialistKey,
  sessionId,
  skills,
  uid,
  onResult,
  onSubmittingChange,
}: RunStandaloneSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
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
    onSubmittingChange?.(true);
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
      onResult(data);
      // Auto-collapse the form so the lifted result has room — user can
      // re-expand to run another input. Keeps the panel focused on the
      // output the user just requested.
      setExpanded(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
      onSubmittingChange?.(false);
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
        </div>
      )}
    </div>
  );
}
