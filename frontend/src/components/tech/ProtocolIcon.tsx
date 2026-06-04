/**
 * Inline SVG glyphs for each tech pillar.
 *
 * Logos can't be redistributed safely (different licenses, drift over
 * time, brand-guidelines violations); these are semantic abstractions
 * that survive a rebrand and stay clean at 16/24/48px. One stroke
 * style, currentColor — they take on the surrounding text color.
 */
type IconKey = "ailang" | "adk" | "a2ui" | "mcp-apps" | "ag-ui" | "a2a";

interface ProtocolIconProps {
  pillar: IconKey;
  className?: string;
}

export function ProtocolIcon({ pillar, className = "h-5 w-5" }: ProtocolIconProps) {
  switch (pillar) {
    case "ailang":
      // Code-bracket + a tight inner line — "parse" as structural reading.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M8 5L3 12l5 7" />
          <path d="M16 5l5 7-5 7" />
          <path d="M10 9h4M10 15h4" />
        </svg>
      );
    case "adk":
      // Four nodes connected — multi-agent orchestration.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="4.5" r="1.8" />
          <circle cx="4.5" cy="12" r="1.8" />
          <circle cx="19.5" cy="12" r="1.8" />
          <circle cx="12" cy="19.5" r="1.8" />
          <path d="M12 6.3v3.9M12 13.8v3.9M6.3 12h3.9M13.8 12h3.9" />
        </svg>
      );
    case "a2ui":
      // Browser window with a structured card inside.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="4" width="18" height="16" rx="1.5" />
          <path d="M3 8h18" />
          <path d="M7 12h10M7 16h6" />
        </svg>
      );
    case "mcp-apps":
      // Plug / socket — interoperable apps.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M9 3v4M15 3v4" />
          <rect x="6" y="7" width="12" height="6" rx="1.5" />
          <path d="M12 13v4" />
          <path d="M8 21h8" />
          <path d="M10 17h4" />
        </svg>
      );
    case "ag-ui":
      // Streaming waveform — SSE event flow.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2 12c2 0 2-4 4-4s2 8 4 8 2-6 4-6 2 4 4 4 2-2 4-2" />
        </svg>
      );
    case "a2a":
      // Two arrows meeting — agent-to-agent handshake.
      return (
        <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 8h14l-3-3M21 16H7l3 3" />
        </svg>
      );
  }
}
