import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Rebuild a NextRequest-like object just well enough for the route handler.
function makeReq(path: string, init: RequestInit & { url?: string } = {}) {
  const url = init.url ?? `http://localhost:3000/api/proxy/${path}`;
  const req = new Request(url, init) as Request & { nextUrl: URL };
  req.nextUrl = new URL(url);
  return req;
}

describe("catch-all proxy route", () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    fetchSpy.mockReset();
    vi.stubGlobal("fetch", fetchSpy);
    process.env.BACKEND_URL = "http://127.0.0.1:1956";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards Authorization: Bearer to the backend", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const { GET } = await import("@/app/api/proxy/[...path]/route");
    const req = makeReq("api/skills", {
      method: "GET",
      headers: { Authorization: "Bearer test-token" },
    });
    const res = await GET(req as never, {
      params: Promise.resolve({ path: ["api", "skills"] }),
    });
    expect(res.status).toBe(200);

    const [calledUrl, calledInit] = fetchSpy.mock.calls[0];
    expect(calledUrl).toBe("http://127.0.0.1:1956/api/skills");
    const headers = new Headers((calledInit as RequestInit).headers);
    expect(headers.get("authorization")).toBe("Bearer test-token");
  });

  it("returns the backend 401 as-is (does not shadow to Next 404)", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Missing Authorization header" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    const { GET } = await import("@/app/api/proxy/[...path]/route");
    const req = makeReq("api/skills", { method: "GET" });
    const res = await GET(req as never, {
      params: Promise.resolve({ path: ["api", "skills"] }),
    });
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body).toEqual({ detail: "Missing Authorization header" });
  });

  // Regression: the iframe-context endpoint (sprint 1.25) returns 204 No
  // Content. The Web Response constructor forbids a body on 204/205/304, so
  // `new Response(arrayBuffer, {status: 204})` throws TypeError and the proxy
  // converts that to a spurious 502 backend_unreachable. Found in deployed-dev
  // E2E run on 2026-05-01 — surfaced as the missing "active bridge" half of
  // the M4 acceptance criterion.
  it("forwards a 204 No Content as 204 (not 502 — null-body status)", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(null, {
        status: 204,
        headers: { "content-type": "application/json" },
      }),
    );
    const { POST } = await import("@/app/api/proxy/[...path]/route");
    const req = makeReq("api/sessions/sess-1/iframe-context", {
      method: "POST",
      headers: { Authorization: "Bearer t", "content-type": "application/json" },
      body: JSON.stringify({ serverId: "ext-apps-map" }),
    });
    const res = await POST(req as never, {
      params: Promise.resolve({ path: ["api", "sessions", "sess-1", "iframe-context"] }),
    });
    expect(res.status).toBe(204);
    expect(res.body).toBeNull();
  });

  it("returns 502 when the backend is unreachable", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const { GET } = await import("@/app/api/proxy/[...path]/route");
    const req = makeReq("api/skills", { method: "GET" });
    const res = await GET(req as never, {
      params: Promise.resolve({ path: ["api", "skills"] }),
    });
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toBe("backend_unreachable");
  });

  it("strips the Host header before forwarding", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    const { GET } = await import("@/app/api/proxy/[...path]/route");
    const req = makeReq("api/skills", {
      method: "GET",
      headers: { host: "example.com", Authorization: "Bearer t" },
    });
    await GET(req as never, {
      params: Promise.resolve({ path: ["api", "skills"] }),
    });
    const headers = new Headers((fetchSpy.mock.calls[0][1] as RequestInit).headers);
    expect(headers.get("host")).toBeNull();
    expect(headers.get("authorization")).toBe("Bearer t");
  });

  describe("SSE streaming", () => {
    it("pipes text/event-stream responses as a ReadableStream (not buffered)", async () => {
      const encoder = new TextEncoder();
      const chunks = [
        'data: {"type":"TEXT_MESSAGE_CHUNK","delta":"Hello"}\n\n',
        'data: {"type":"TEXT_MESSAGE_CHUNK","delta":" world"}\n\n',
        'data: {"type":"RUN_FINISHED"}\n\n',
      ];
      const stream = new ReadableStream({
        start(controller) {
          for (const chunk of chunks) {
            controller.enqueue(encoder.encode(chunk));
          }
          controller.close();
        },
      });
      fetchSpy.mockResolvedValueOnce(
        new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      );

      const { POST } = await import("@/app/api/proxy/[...path]/route");
      const req = makeReq("api/skill/test-skill/stream", {
        method: "POST",
        url: "http://localhost:3000/api/proxy/api/skill/test-skill/stream",
      });
      const res = await POST(req as never, {
        params: Promise.resolve({ path: ["api", "skill", "test-skill", "stream"] }),
      });

      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toContain("text/event-stream");
      // The body must be a ReadableStream, not a buffered Uint8Array
      expect(res.body).toBeInstanceOf(ReadableStream);
    });

    it("reads all SSE chunks incrementally from the piped stream", async () => {
      const encoder = new TextEncoder();
      const sentChunks = [
        'data: {"type":"TEXT_MESSAGE_CHUNK","delta":"tok1"}\n\n',
        'data: {"type":"TEXT_MESSAGE_CHUNK","delta":"tok2"}\n\n',
      ];
      const stream = new ReadableStream({
        start(controller) {
          for (const chunk of sentChunks) {
            controller.enqueue(encoder.encode(chunk));
          }
          controller.close();
        },
      });
      fetchSpy.mockResolvedValueOnce(
        new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream; charset=utf-8" },
        }),
      );

      const { POST } = await import("@/app/api/proxy/[...path]/route");
      const req = makeReq("api/skill/s/stream", {
        method: "POST",
        url: "http://localhost:3000/api/proxy/api/skill/s/stream",
      });
      const res = await POST(req as never, {
        params: Promise.resolve({ path: ["api", "skill", "s", "stream"] }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      const received: string[] = [];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        received.push(decoder.decode(value));
      }

      expect(received).toHaveLength(sentChunks.length);
      expect(received.join("")).toContain("tok1");
      expect(received.join("")).toContain("tok2");
    });

    it("buffers non-SSE responses normally (regression guard)", async () => {
      const payload = { skills: [] };
      fetchSpy.mockResolvedValueOnce(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

      const { GET } = await import("@/app/api/proxy/[...path]/route");
      const req = makeReq("api/skills", { method: "GET" });
      const res = await GET(req as never, {
        params: Promise.resolve({ path: ["api", "skills"] }),
      });

      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body).toEqual(payload);
    });
  });
});
