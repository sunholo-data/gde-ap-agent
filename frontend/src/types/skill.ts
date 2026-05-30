/**
 * Skill types — mirrors backend/db/models.py SkillConfig.
 *
 * Layer 1: Agent Skills spec fields (name, description, instructions, skillMetadata)
 * Layer 2: Aitana platform metadata (skillId, displayName, accessControl, etc.)
 *
 * Generated from: backend SkillConfig.model_json_schema(by_alias=True)
 * Source of truth: backend/db/models.py
 */

export interface SkillMetadata {
  author: string;
  version: string;
  model: string;
  thinkingModel?: string | null;
  tools: string[];
  toolConfigs: Record<string, Record<string, unknown>>;
  subSkills: string[];
}

export interface AccessControl {
  type: "private" | "public" | "domain" | "specific";
  domain?: string | null;
  emails?: string[] | null;
}

export interface ProtocolConfig {
  enabled: boolean;
}

export interface Protocols {
  mcp: ProtocolConfig;
  a2a: ProtocolConfig;
  agui: ProtocolConfig;
  a2ui: ProtocolConfig;
  mcpApps: ProtocolConfig;
}

export interface Skill {
  // Layer 1: Agent Skills spec
  name: string;
  description: string;
  instructions: string;
  skillMetadata: SkillMetadata;
  references: Record<string, string>;
  assets: Record<string, string>;

  // Layer 2: Aitana platform metadata
  skillId: string;
  slug?: string | null;
  displayName: string;
  avatar: string;
  ownerEmail: string;
  ownerId: string;
  accessControl: AccessControl;
  protocols: Protocols;
  initialMessage: string;
  tags: string[];
  featured: boolean;
  usageCount: number;
  createdAt: number;
  updatedAt: number;
  v5AssistantId?: string | null;
}
