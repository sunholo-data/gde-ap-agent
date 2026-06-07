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

/**
 * Public-host the agent card claims it lives at.
 *
 * The FastAPI backend has no idea what URL the outside world reaches it
 * by — it sits as a sidecar behind this Next.js ingress. Left untouched,
 * the card advertises `http://localhost:1956` (the backend's PUBLIC_BASE_URL
 * fallback), which means a peer A2A agent or Gemini Enterprise can discover
 * the card but cannot actually invoke any skill on it. This route is the
 * one layer that knows the real public URL, so it rewrites the `url` field
 * to match the incoming request's origin.
 *
 * Cloud Run terminates TLS at the GFE and forwards via `X-Forwarded-Proto`;
 * NextRequest.nextUrl already accounts for that, so `req.nextUrl.origin`
 * is the right authority to advertise.
 */
function publicOrigin(req: NextRequest): string {
  // Prefer forwarded headers (Cloud Run GFE always sets these) over
  // req.nextUrl.origin so we never accidentally advertise an internal host.
  const proto = req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "");
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? req.nextUrl.host;
  return `${proto}://${host}`;
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const url = `${BACKEND_URL}/.well-known/agent.json`;
  try {
    const upstream = await fetch(url, {
      method: "GET",
      headers: filterRequestHeaders(req.headers),
      cache: "no-store",
    });
    const headers = filterResponseHeaders(upstream.headers);
    const contentType = upstream.headers.get("content-type") ?? "";

    // Pass non-JSON or non-2xx responses through untouched so error bodies
    // are not silently rewritten into something they aren't.
    if (!contentType.includes("application/json") || !upstream.ok) {
      const passthrough = await upstream.arrayBuffer();
      return new NextResponse(passthrough, { status: upstream.status, headers });
    }

    const card = (await upstream.json()) as Record<string, unknown>;
    card.url = publicOrigin(req);
    const rewritten = JSON.stringify(card);
    headers.set("content-type", "application/json");

    // Vary: ensure X-A2A-Extensions is in OUR Vary header so caches between
    // us and an A2A peer key responses by capability set. Next.js's
    // framework wrapper appends its own Vary entries (rsc / next-router-*)
    // for React-Server-Components routing — on the wire that produces two
    // Vary headers, which RFC 7234 caches merge correctly but older
    // intermediaries can mishandle. By asserting Vary ourselves we
    // guarantee the cache-key-relevant token is in a single canonical line
    // we control; Next's separate line stays for its own routing concerns.
    const existingVary = headers.get("vary") ?? "";
    headers.set(
      "vary",
      existingVary.toLowerCase().includes("x-a2a-extensions")
        ? existingVary
        : existingVary
          ? `${existingVary}, X-A2A-Extensions`
          : "X-A2A-Extensions",
    );

    return new NextResponse(rewritten, { status: upstream.status, headers });
  } catch (err) {
    return NextResponse.json(
      { error: "backend_unreachable", message: String(err) },
      { status: 502 },
    );
  }
}
