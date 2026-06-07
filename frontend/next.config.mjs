/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL,
  },
  serverRuntimeConfig: {
    MAILGUN_WEBHOOK_SECRET: process.env.MAILGUN_WEBHOOK_SECRET,
  },
  // Proxy /a2a/* to the FastAPI sidecar.
  //
  // Next.js owns the public ingress; FastAPI sits at 127.0.0.1:1956 as a
  // sidecar. The /api/proxy/* catch-all handles the in-app API surface,
  // and /.well-known/agent.json has its own route handler that rewrites
  // the card's `url` field. But the strict A2A invocation surface ADK's
  // to_a2a mounts at /a2a is a different shape: pure passthrough, no body
  // rewriting, including streaming POSTs for message/sendSubscribe.
  // A Next.js rewrite is the right pattern — no per-request handler
  // overhead, streaming-safe out of the box.
  //
  // Without this, every peer probing card.url gets a Next.js HTML 404
  // page even though the FastAPI mount is live. We confirmed via
  // `curl /a2a/.well-known/agent.json` returning HTML with
  // `x-nextjs-cache: HIT` while the underlying FastAPI was healthy.
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:1956'
    return [
      { source: '/a2a', destination: `${backend}/a2a/` },
      { source: '/a2a/:path*', destination: `${backend}/a2a/:path*` },
    ]
  },
}

export default nextConfig
