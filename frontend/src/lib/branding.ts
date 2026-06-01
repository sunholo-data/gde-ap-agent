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
  appName: "GDE AP Agent",

  /** One-line product tagline shown under the logo on the welcome screen. */
  tagline: "AI-Powered Accounts Payable",

  /** Long form description used in <meta name="description">. */
  description: "Autonomous accounts-payable processing — invoice intake, extraction, validation, and posting powered by Google ADK multi-agent AI.",

  /** Public-facing logo paths. Swap the files in /public/images/logo/ to
   * rebrand without touching this object. */
  logo: {
    /** Browser tab favicon (SVG — works in all modern browsers). */
    favicon: "/images/logo/gde-ap-agent-logo.svg",
    /** Welcome-screen mark (SVG). */
    heroAnimated: "/images/logo/gde-ap-agent-logo.svg",
    /** Square chat-message-bubble avatar (SVG). */
    chatAvatar: "/images/logo/gde-ap-agent-avatar.svg",
  },

  /** Contact / community links exposed in CONTRIBUTING + workshop docs. */
  contact: {
    email: "mark@aitanalabs.com",
    githubRepo: "https://github.com/sunholo-data/gde-ap-agent",
  },
} as const;

export type Branding = typeof BRANDING;
