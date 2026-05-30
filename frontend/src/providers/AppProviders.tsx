"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "@/contexts/AuthContext";

/**
 * Composite provider tree. PHASE1-UI will add A2UI + CopilotKit providers here.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
