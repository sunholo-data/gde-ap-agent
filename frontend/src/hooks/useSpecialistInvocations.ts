"use client";

import { useEffect, useRef, useState } from "react";
import type { ToolCallState } from "@/hooks/useSkillAgent";
import { SPECIALIST_KEYS, specialistKeyForToolName, type SpecialistKey } from "@/lib/auditViewFlag";

export type InvocationStatus = "idle" | "active" | "done" | "error";

export interface InvocationRecord {
  /** ToolCallState.id of the orchestrator tool call that triggered this run */
  id: string;
  /** Raw tool-call name (e.g. "transfer_to_docparse") */
  name: string;
  status: InvocationStatus;
  /** Wall-clock ms when first seen */
  startedAt: number;
  /** Wall-clock ms when status became done/error; null while running */
  endedAt: number | null;
  /** Tool-call arguments JSON string (orchestrator's input to this specialist) */
  argsJson?: string;
  /** Tool-call result content from the specialist */
  resultContent?: string;
}

export interface SpecialistState {
  /** Most recent invocation (active or last completed). Null until first call. */
  current: InvocationRecord | null;
  /** Most recent N invocations in chronological order. Up to 5. */
  history: InvocationRecord[];
  /** Convenience: current.status with idle fallback. */
  status: InvocationStatus;
}

export type SpecialistInvocations = Record<SpecialistKey, SpecialistState>;

const EMPTY_STATE: SpecialistState = { current: null, history: [], status: "idle" };

function statusFromToolCall(tc: ToolCallState): InvocationStatus {
  if (tc.status === "running") return "active";
  if (tc.status === "error") return "error";
  return "done";
}

/**
 * Reduces the orchestrator's `toolCalls` stream into per-specialist
 * invocation state. Drives the SpecialistChip + Audit View panel.
 *
 * Identity is by `ToolCallState.id` — we keep timestamps in a ref so we
 * don't lose `startedAt` between renders. The hook also persists the
 * latest record per specialist into sessionStorage so forms can prefill
 * "Load from last X" and a refresh recovers the audit-view state.
 */
export function useSpecialistInvocations(
  toolCalls: ToolCallState[],
  sessionId: string | null,
): SpecialistInvocations {
  const [state, setState] = useState<SpecialistInvocations>(() => emptyAll());

  // Per-id startedAt timestamps so a row that flips from running → success
  // doesn't lose its origin time. Same for endedAt — once a tool call
  // transitions out of "active", its end time MUST be frozen; otherwise
  // every subsequent re-render of this hook (each new tool call event
  // anywhere in the stream) updates `endedAt = Date.now()` and the
  // displayed latency for already-completed specialists keeps ticking
  // upward on the chip ("70.8s" → "75.2s" → "82.1s" with no run
  // happening). The user notices as "the timers are jumpy."
  const startedAtRef = useRef<Map<string, number>>(new Map());
  const endedAtRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const next = emptyAll();
    const grouped = new Map<SpecialistKey, InvocationRecord[]>();
    for (const key of SPECIALIST_KEYS) grouped.set(key, []);

    for (const tc of toolCalls) {
      const key = specialistKeyForToolName(tc.name);
      if (!key) continue;

      let startedAt = startedAtRef.current.get(tc.id);
      if (startedAt === undefined) {
        startedAt = Date.now();
        startedAtRef.current.set(tc.id, startedAt);
      }
      const status = statusFromToolCall(tc);
      let endedAt: number | null;
      if (status === "active") {
        endedAt = null;
      } else {
        // Freeze on the first non-active observation; preserve thereafter.
        let frozen = endedAtRef.current.get(tc.id);
        if (frozen === undefined) {
          frozen = Date.now();
          endedAtRef.current.set(tc.id, frozen);
        }
        endedAt = frozen;
      }

      const record: InvocationRecord = {
        id: tc.id,
        name: tc.name,
        status,
        startedAt,
        endedAt,
        argsJson: tc.argsJson,
        resultContent: tc.resultContent,
      };
      grouped.get(key)!.push(record);
    }

    for (const key of SPECIALIST_KEYS) {
      const records = grouped.get(key)!;
      if (records.length === 0) continue;
      // When the same emit_* tool fires multiple times in one turn
      // (Gemini's tool-use loop hit the idempotency guard), every
      // re-call after the first returns the STOP_AFTER_EMIT_MESSAGE
      // confirmation rather than the real structured payload. The
      // user wants to see the CANONICAL emit — the first one with a
      // result that ISN'T the stop message. Fall back to the latest
      // record when none look canonical (eg. the run is still
      // active and the first call hasn't returned yet).
      const canonical = records.find(
        (r) =>
          r.status === "done" &&
          r.resultContent &&
          !/stop\.?\s*do not call this tool again/i.test(r.resultContent),
      );
      const current = canonical ?? records[records.length - 1];
      const history = records.slice(-5);
      next[key] = { current, history, status: current.status };

      // Persist the most-recent completed structured output so
      // "Load from last X" pre-fills survive a refresh.
      if (sessionId && current.status === "done" && current.resultContent) {
        try {
          sessionStorage.setItem(
            `ap-audit-last-output:${sessionId}:${key}`,
            current.resultContent,
          );
        } catch {
          // sessionStorage can throw in private mode / strict CSP; ignore.
        }
      }
    }

    setState(next);
  }, [toolCalls, sessionId]);

  return state;
}

function emptyAll(): SpecialistInvocations {
  return {
    docparse: EMPTY_STATE,
    validator: EMPTY_STATE,
    poster: EMPTY_STATE,
  };
}

/** Read the cached last result for "Load from last X" pre-fill. */
export function readLastOutput(sessionId: string | null, key: SpecialistKey): string | null {
  if (!sessionId) return null;
  try {
    return sessionStorage.getItem(`ap-audit-last-output:${sessionId}:${key}`);
  } catch {
    return null;
  }
}
