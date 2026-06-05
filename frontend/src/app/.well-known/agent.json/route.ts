// A2A discovery endpoint at /.well-known/agent.json — proxies to the
// backend sidecar so external crawlers see the card without the
// /api/proxy prefix.
//
// Why this exists
// ---------------
// In Cloud Run we ship two containers: a Next.js frontend (which owns
// the public ingress) and a Python backend (sidecar, internal port
// 1956). Only the Next route table is reachable from outside, so a
// hit to https://<host>/.well-known/agent.json was returning a Next
// 404 even though the backend HAS the handler. A2A crawlers follow
// RFC 8615 and look at the unprefixed well-known URI — they don't
// know about `/api/proxy/...`, so without this route the discovery
// card is effectively invisible to the rest of the agent ecosystem.
//
// This route is a minimal byte-passthrough of the upstream response
// (including the `X-A2A-Extensions` capability-negotiation header and
// the `Vary` header set by the FastAPI handler). The request's
// `X-A2A-Extensions` header is forwarded upstream so capability
// negotiation works for external clients.

import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:1956";

// Mirrors the catch-all proxy's hop-by-hop / Next-internal block list.
// `X-A2A-Extensions` is NOT blocked — we want it to reach the backend so
// /protocols/a2a.py:agent_card can negotiate against it.
const BLOCKED_REQUEST_HEADERS = new Set([
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "upgrade",
  "x-middleware-invoke",
  "x-invoke-path",
  "x-invoke-query",
]);

const BLOCKED_RESPONSE_HEADERS = new Set([
  "connection",
  "content-length",
  "transfer-encoding",
  "keep-alive",
]);

function filterRequestHeaders(headers: Headers): Headers {
  const out = new Headers();
  headers.forEach((value, key) => {
    if (!BLOCKED_REQUEST_HEADERS.has(key.toLowerCase())) {
      out.set(key, value);
    }
  });
  return out;
}

function filterResponseHeaders(headers: Headers): Headers {
  const out = new Headers();
  headers.forEach((value, key) => {
    if (!BLOCKED_RESPONSE_HEADERS.has(key.toLowerCase())) {
      out.set(key, value);
    }
  });
  return out;
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const url = `${BACKEND_URL}/.well-known/agent.json`;
  try {
    const upstream = await fetch(url, {
      method: "GET",
      headers: filterRequestHeaders(req.headers),
      cache: "no-store",
    });
    const body = await upstream.arrayBuffer();
    return new NextResponse(body, {
      status: upstream.status,
      headers: filterResponseHeaders(upstream.headers),
    });
  } catch (err) {
    return NextResponse.json(
      { error: "backend_unreachable", message: String(err) },
      { status: 502 },
    );
  }
}
