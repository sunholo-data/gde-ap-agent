import type { ReactElement } from "react";
import type { Skill } from "@/types/skill";

export interface SkillMeta {
  tagline: string;
  description: string;
  isEntryPoint: boolean;
  subAgentCount?: number;
  icon: ReactElement;
}

// Icons sized for skill tabs (h-4 w-4)
export function OrchestratorIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="8" cy="8" r="2.5" />
      <circle cx="8" cy="2.5" r="1.5" />
      <circle cx="13" cy="11.5" r="1.5" />
      <circle cx="3" cy="11.5" r="1.5" />
      <path d="M8 5v1.5M6.7 9.2l-2.5 1.5M9.3 9.2l2.5 1.5" strokeLinecap="round" />
    </svg>
  );
}

export function DocParseIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M3 2h7l3 3v9H3V2z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 2v3h3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5.5 8.5h5M5.5 10.5h3" strokeLinecap="round" />
      <circle cx="11.5" cy="11.5" r="2.5" />
      <path d="M13.5 13.5l1.5 1.5" strokeLinecap="round" />
    </svg>
  );
}

export function ValidatorIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1.5L2.5 4v3.5c0 3.5 2.5 5.8 5.5 6.8 3-1 5.5-3.3 5.5-6.8V4L8 1.5z" strokeLinejoin="round" />
      <path d="M5.5 8l1.5 1.5 3-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PosterIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="5" width="9" height="9" rx="1" strokeLinejoin="round" />
      <path d="M5 5V4a3 3 0 0 1 6 0v1" strokeLinecap="round" />
      <path d="M6.5 9l1.5 1.5 1.5-1.5M8 10.5V7.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13 8l1.5-1.5M13 5.5l1.5 1.5" strokeLinecap="round" />
    </svg>
  );
}

const META: Record<string, SkillMeta> = {
  orchestrator: {
    tagline: "AP Orchestrator",
    description:
      "Entry point for the Accounts Payable pipeline. Routes invoices through 3 specialist sub-agents — DocParse → Validator → Poster — and produces a full audit trail.",
    isEntryPoint: true,
    subAgentCount: 3,
    icon: <OrchestratorIcon />,
  },
  docparse: {
    tagline: "Document Parser",
    description:
      "Extracts structured data from invoices: vendor, line items, tax, GL codes. Feeds clean JSON to the Validator.",
    isEntryPoint: false,
    icon: <DocParseIcon />,
  },
  validator: {
    tagline: "AP Validator",
    description:
      "Validates extracted invoice data against business rules: PO matching, vendor whitelist, GL code mapping, duplicate checks.",
    isEntryPoint: false,
    icon: <ValidatorIcon />,
  },
  poster: {
    tagline: "ERP Poster",
    description:
      "Posts approved invoices to the ERP ledger and records the complete audit trail with timestamps and agent signatures.",
    isEntryPoint: false,
    icon: <PosterIcon />,
  },
};

function matchKey(skill: Skill): string | null {
  const id = [skill.slug, skill.name, skill.skillId].filter(Boolean).join(" ").toLowerCase();
  if (id.includes("orchestrator")) return "orchestrator";
  if (id.includes("docparse") || id.includes("doc-parse") || id.includes("doc_parse")) return "docparse";
  if (id.includes("validator")) return "validator";
  if (id.includes("poster")) return "poster";
  return null;
}

export function getSkillMeta(skill: Skill): SkillMeta | null {
  const key = matchKey(skill);
  return key ? META[key] : null;
}
