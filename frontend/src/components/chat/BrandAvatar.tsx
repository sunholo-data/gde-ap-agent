"use client";

import { BRANDING } from "@/lib/branding";

/**
 * Bot avatar shown next to each ap-orchestrator message bubble. Quietly
 * styled — soft primary-tinted background, hairline ring, app mark on top.
 * Replaces the prior amber gradient which clashed with the light-theme
 * parse-blue palette.
 */
export function BrandAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-primary/20 bg-primary/5 ring-1 ring-inset ring-primary/5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={BRANDING.logo.chatAvatar}
        alt={BRANDING.appName}
        className="h-4 w-4"
      />
    </div>
  );
}
