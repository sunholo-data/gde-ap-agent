"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/apiClient";

interface SkillMeta {
  displayName: string;
  ownerId: string | null;
  slug: string | null;
  /** MCP server IDs this skill is configured to use, sourced from
   * skillMetadata.toolConfigs.mcp.servers. Empty array if none. The chat
   * page passes this to MessageBubble so MCPAppToolCallRouter can decide
   * which tool calls have a UI surface. */
  mcpServerIds: readonly string[];
  loading: boolean;
}

interface SkillResponse {
  displayName?: string;
  display_name?: string;
  name?: string;
  ownerId?: string;
  owner_id?: string;
  slug?: string | null;
  skillMetadata?: { toolConfigs?: { mcp?: { servers?: unknown } } };
  skill_metadata?: { toolConfigs?: { mcp?: { servers?: unknown } } };
}

function extractMcpServerIds(data: SkillResponse): readonly string[] {
  const meta = data.skillMetadata ?? data.skill_metadata;
  const servers = meta?.toolConfigs?.mcp?.servers;
  if (!Array.isArray(servers)) return [];
  return servers.filter((s): s is string => typeof s === "string");
}

export function useSkillMeta(skillId: string): SkillMeta {
  const [displayName, setDisplayName] = useState<string>(skillId.slice(0, 8));
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [slug, setSlug] = useState<string | null>(null);
  const [mcpServerIds, setMcpServerIds] = useState<readonly string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchWithAuth(`/api/proxy/api/skills/${skillId}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as SkillResponse;
        if (!cancelled) {
          const display = data.displayName || data.display_name || data.name || skillId.slice(0, 8);
          setDisplayName(display);
          setOwnerId(data.ownerId || data.owner_id || null);
          setSlug(data.slug ?? null);
          setMcpServerIds(extractMcpServerIds(data));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
        // displayName stays as truncated UUID fallback; mcpServerIds stays empty
      });
    return () => {
      cancelled = true;
    };
  }, [skillId]);

  return { displayName, ownerId, slug, mcpServerIds, loading };
}
