"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";

export interface SlugResolution {
  skillId: string | null;
  loading: boolean;
  notFound: boolean;
  error: string | null;
}

/**
 * Resolve a `/chat/@{ownerId}/{slug}` path to the underlying skill UUID.
 *
 * The friendly URL is a display alias. Internally everything (SSE streaming,
 * sessions, doc context) keys off the UUID, so we resolve once on mount and
 * hand the UUID to the chat surface.
 *
 * Returns `notFound: true` when the path doesn't match `[@ownerId, slug]`
 * shape, when the backend returns 404, or when the slug isn't visible to
 * the caller (private skill, wrong owner, etc.). Callers render their 404
 * branch on `notFound`.
 *
 * Pass `enabled=false` while Firebase auth is still hydrating — otherwise
 * fetchWithAuth fires before getIdToken() has a token, the request goes
 * unauthenticated, the backend returns 401, and the hook flips to error
 * state before the user is signed in. The chat page passes `!authLoading`.
 */
export function useSlugResolution(path: string[] | undefined, enabled: boolean = true): SlugResolution {
  const [skillId, setSkillId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [notFound, setNotFound] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSkillId(null);
    setError(null);
    setNotFound(false);
    setLoading(true);

    if (!enabled) {
      // Stay in loading state; the parent renders a spinner until auth resolves.
      return () => undefined;
    }

    // Next.js URL-encodes route segments before placing them into `params`,
    // so `/chat/@foo/slug` arrives here as `["%40foo", "slug"]`. Decode each
    // segment before pattern-matching, otherwise `startsWith("@")` fails
    // silently and we render "Skill not found" without ever firing the fetch.
    const decoded = path?.map((seg) => {
      try {
        return decodeURIComponent(seg);
      } catch {
        return seg;
      }
    });

    if (!decoded || decoded.length !== 2 || !decoded[0].startsWith("@") || decoded[0].length < 2) {
      setNotFound(true);
      setLoading(false);
      return () => undefined;
    }

    const ownerId = decoded[0].slice(1);
    const slug = decoded[1];

    fetchWithAuth(
      `/api/proxy/api/skills/by-slug/${encodeURIComponent(ownerId)}/${encodeURIComponent(slug)}`,
    )
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 404) {
          setNotFound(true);
          setLoading(false);
          return;
        }
        if (!res.ok) {
          setError(`HTTP ${res.status}`);
          setLoading(false);
          return;
        }
        const data = (await res.json()) as Record<string, unknown>;
        if (cancelled) return;
        // Accept both camelCase (preferred) and snake_case (defensive — older
        // FastAPI deployments may not be configured with response_model_by_alias).
        const resolvedSkillId =
          (data.skillId as string | undefined) ??
          (data.skill_id as string | undefined);
        if (!resolvedSkillId) {
          setNotFound(true);
        } else {
          setSkillId(resolvedSkillId);
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "fetch failed");
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // path is an array reference that changes per render; key on its content.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path?.join("/"), enabled]);

  return { skillId, loading, notFound, error };
}
