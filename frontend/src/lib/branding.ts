/**
 * Branding — the single file a public fork rebrands.
 *
 * Every user-visible product string in chrome (page titles, marketing
 * copy, contact email, the welcome screen logo path) lives here. A
 * downstream fork rewrites this one file; everything else is generic
 * protocol-stack code.
 *
 * Upstream identity: Sunholo (the public template at
 * sunholo-data/ai-protocol-platform). Downstream consumers (Aitana,
 * AIPLA, etc.) override this object in their own forks.
 *
 * NOT in scope here:
 * - Skill content (lives in Firestore + skill templates)
 * - User-uploaded assets (lives in GCS)
 * - SVG logo file itself (lives in /public/images/logo/, swap the file)
 */

/**
 * Citation URI scheme used by the agent backend to embed document-block links.
 * Format: `{CITATION_SCHEME}://doc/{docId}/block/{blockId}`
 *
 * Forks: set NEXT_PUBLIC_CITATION_SCHEME in .env.local (or Cloud Build substitution)
 * to rebrand this URI without touching component code.
 */
export const CITATION_SCHEME =
  process.env.NEXT_PUBLIC_CITATION_SCHEME ?? "inline-citation";

/**
 * Internal transport field name injected into MCP App postMessage payloads.
 * Forks: set NEXT_PUBLIC_APP_SLUG to change the prefix (e.g. "myapp" → "__myappTransport").
 */
export const TRANSPORT_FIELD = `__${process.env.NEXT_PUBLIC_APP_SLUG ?? "platform"}Transport`;

export const BRANDING = {
  /** Short product name used in page <title>, banners, marketing hero. */
  appName: "ailang-parse · AP Showcase",

  /** One-line product tagline shown under the logo on the welcome screen. */
  tagline: "Universal document parsing in AILANG — invoice intake, extraction, validation, posting.",

  /** Long form description used in <meta name="description">. */
  description: "A live showcase of ailang-parse — deterministic invoice extraction running inside a Google ADK multi-agent AP pipeline. Part of the AILANG family.",

  /** Public-facing logo paths. Swap the files in /public/images/logo/ to
   * rebrand without touching this object. */
  logo: {
    /** Browser tab favicon (SVG — works in all modern browsers). */
    favicon: "/images/logo/ailang-parse-logo.svg",
    /** Welcome-screen mark (SVG). */
    heroAnimated: "/images/logo/ailang-parse-hero.svg",
    /** Square chat-message-bubble avatar (SVG). */
    chatAvatar: "/images/logo/ailang-parse-logo.svg",
    /** Small attribution mark used to indicate AILANG family membership. */
    familyMark: "/images/logo/ailang-logo.svg",
  },

  /** Outbound links to the parent project family. */
  links: {
    ailang: "https://ailang.sunholo.com",
    ailangParse: "https://www.sunholo.com/ailang-parse",
    sunholo: "https://www.sunholo.com",
  },

  /** Contact / community links exposed in CONTRIBUTING + workshop docs. */
  contact: {
    email: "mark@aitanalabs.com",
    githubRepo: "https://github.com/sunholo-data/gde-ap-agent",
  },

  /** Routes + copy for the AP showcase landing experience.
   * The landing page funnels visitors to a single demo flow; the tech page
   * exists for judges who want the protocol-stack story. */
  demo: {
    /** Friendly slug-route into the AP orchestrator chat. */
    chatHref: "/chat/@gde-ap-agent/ap-orchestrator",
    /** Judges-facing technical breakdown route. */
    techHref: "/tech",
    /** Hero copy. Two-line headline split for typographic control. */
    heroEyebrow: "Live demo · Google for Startups AI Agents Challenge",
    heroLineA: "Invoices in.",
    heroLineB: "Audit-grade postings out.",
    heroBody:
      "Drop an invoice. Watch a four-agent ADK pipeline extract it deterministically with AILANG Parse, validate against the vendor master, decide a posting, and surface every step as an inspectable artifact.",
    ctaPrimary: "Try the AP demo",
    ctaSecondary: "How it works",
    /** Six tech pillars used on landing + /tech. AILANG leads — it's the
     * differentiator (everything else is industry protocols; AILANG is ours).
     * Each pillar carries a canonical spec/docs link surfaced on the landing
     * stripe and the /tech deep-dive. */
    pillars: [
      {
        key: "ailang",
        label: "AILANG",
        tagline: "Deterministic parse + effect-typed code",
        spec: "https://ailang.sunholo.com",
      },
      {
        key: "adk",
        label: "Google ADK",
        tagline: "Multi-agent orchestration",
        spec: "https://google.github.io/adk-docs/",
      },
      {
        key: "a2ui",
        label: "A2UI",
        tagline: "Declarative agent UI",
        spec: "https://github.com/agentic-protocols/a2ui",
      },
      {
        key: "mcp-apps",
        label: "MCP Apps",
        tagline: "Sandboxed iframe artifacts",
        spec: "https://modelcontextprotocol.io",
      },
      {
        key: "ag-ui",
        label: "AG-UI",
        tagline: "Streaming events to the client",
        spec: "https://ag-ui.com",
      },
      {
        key: "a2a",
        label: "A2A",
        tagline: "Cross-agent discovery",
        spec: "https://a2aproject.dev",
      },
    ],
  },
} as const;

export type Branding = typeof BRANDING;
