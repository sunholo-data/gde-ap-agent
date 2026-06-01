import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({
    status: "ok",
    service: "gde-ap-agent-frontend",
    commit: process.env.COMMIT_SHA ?? "unknown",
  });
}
