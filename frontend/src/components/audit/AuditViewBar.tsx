"use client";

import { SpecialistChip } from "./SpecialistChip";
import { SPECIALIST_KEYS, type SpecialistKey } from "@/lib/auditViewFlag";
import type { SpecialistInvocations } from "@/hooks/useSpecialistInvocations";

interface AuditViewBarProps {
  invocations: SpecialistInvocations;
  openKey: SpecialistKey | null;
  onSelect: (key: SpecialistKey) => void;
}

/**
 * Horizontal row of three SpecialistChips that replaces the legacy
 * specialist tabs in the top SkillsBar. Wired by useSpecialistInvocations
 * → onSelect opens the InspectorPanel for that specialist.
 */
export function AuditViewBar({ invocations, openKey, onSelect }: AuditViewBarProps) {
  return (
    <div
      className="flex items-center gap-1.5"
      data-testid="audit-view-bar"
      role="group"
      aria-label="Specialist audit views"
    >
      {SPECIALIST_KEYS.map((key) => (
        <SpecialistChip
          key={key}
          specialistKey={key}
          state={invocations[key]}
          active={openKey === key}
          onClick={() => onSelect(key)}
        />
      ))}
    </div>
  );
}
