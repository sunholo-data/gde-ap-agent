"use client";

import { BRANDING } from "@/lib/branding";

export function BrandAvatar() {
  return (
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-orange-400 to-orange-600">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={BRANDING.logo.chatAvatar}
        alt={BRANDING.appName}
        className="h-5 w-5"
      />
    </div>
  );
}
