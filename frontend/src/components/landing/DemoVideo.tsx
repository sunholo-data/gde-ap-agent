import { BRANDING } from "@/lib/branding";

/**
 * Landing video — 2-minute walkthrough of the AP pipeline. Sits between
 * the hero and the protocol stripe so a visitor who lands cold can watch
 * the full story before scrolling into pillars + demo steps. 16:9 aspect
 * locked via padding-bottom trick to avoid layout shift on slow networks.
 */
export function DemoVideo() {
  return (
    <section className="border-y border-border bg-muted/10">
      <div className="mx-auto w-full max-w-7xl px-6 py-14 md:px-10 md:py-20">
        <div className="mb-6 flex items-end justify-between">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            2-minute walkthrough
          </h2>
          <a
            href={BRANDING.demo.videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
          >
            Watch on YouTube ↗
          </a>
        </div>

        <div className="relative w-full overflow-hidden rounded-lg border border-border bg-background shadow-[0_2px_20px_rgba(0,0,0,0.04)]">
          <div className="relative w-full" style={{ paddingBottom: "56.25%" }}>
            <iframe
              src={BRANDING.demo.videoEmbedUrl}
              title={BRANDING.demo.videoTitle}
              loading="lazy"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              referrerPolicy="strict-origin-when-cross-origin"
              allowFullScreen
              className="absolute inset-0 h-full w-full"
            />
          </div>
        </div>

        <p className="mt-4 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          End-to-end: AG-UI pipeline streaming, A2UI invoice review card, MCP
          App vendor knowledge graph with bidirectional citation-to-chat clicks.
          Built on Google ADK; no Gemini Pro tokens, no LLM at the workflow
          layer.
        </p>
      </div>
    </section>
  );
}
