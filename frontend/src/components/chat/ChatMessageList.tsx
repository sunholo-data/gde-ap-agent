// Workshop W5b — AG-UI: text events → chat bubbles
// ChatMessageList maps AG-UI messages[] from useSkillAgent to MessageBubble /
// StreamingBubble. All state transitions are driven by TEXT_MESSAGE_START /
// CONTENT / END events — no custom event types, no polling.
// Auto-scroll tracks whether the user is near the bottom; if they've scrolled
// up, a "↓ New message" badge appears instead of forcing them back down.
// See: docs/talks/workshop.md §W5

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StreamError, SkillMessage, ToolCallState } from "@/hooks/useSkillAgent";
import type { ActiveDocumentContext } from "@/components/chat/ContextBanner";
import { ContextBanner } from "@/components/chat/ContextBanner";
import { BRANDING } from "@/lib/branding";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";
import { TypingIndicator } from "./TypingIndicator";
import type React from "react";

interface ChatMessageListProps {
  messages: SkillMessage[];
  initialMessages?: SkillMessage[];
  historyError?: string | null;
  toolCalls: ToolCallState[];
  thinkingContent: string;
  isThinking: boolean;
  isLoading: boolean;
  error: StreamError | null;
  skillId: string;
  userInitial: string;
  userDisplayName: string;
  activeDocumentContext?: ActiveDocumentContext | null;
  navigateToBlock?: (docId: string, blockId: string) => void;
  onAction: (event: { actionName: string; context: Record<string, unknown> }) => void;
  errorBanner?: React.ReactNode;
  /**
   * Server-authored stage label from AG-UI STAGE_PROGRESS Custom events,
   * surfaced inside the TypingIndicator. Decouples perceived TTFT from
   * real model TTFT — see docs/design/v6.1.0/ttft-instrumentation.md.
   */
  stageLabel?: string | null;
  /** MCP server IDs configured for the current skill (from
   * useSkillMeta.mcpServerIds) — passed to MessageBubble so
   * MCPAppToolCallRouter can attribute tool calls to a server and decide
   * which have a UI surface. Empty array if the skill has no MCP servers. */
  mcpServerIds?: readonly string[];
  /** Active iframe → host bridge: when an MCP App iframe sends a
   * notification, the adapter translates it to a chat string and this
   * callback (typically wired to useSkillAgent.sendMessage) appends it as
   * the next user turn. */
  onChatMessage?: (text: string) => void;
  /** Current chat session id — threaded to MessageBubble →
   * MCPAppToolCallRouter so iframe `ui/update-model-context` pushes can
   * POST to /api/proxy/api/sessions/{id}/iframe-context (sprint 1.25). */
  sessionId?: string | null;
}

const SCROLL_THRESHOLD = 100;

export function ChatMessageList({
  messages,
  initialMessages,
  historyError,
  toolCalls,
  thinkingContent,
  isThinking,
  isLoading,
  error,
  skillId,
  userInitial,
  userDisplayName,
  activeDocumentContext,
  navigateToBlock,
  onAction,
  errorBanner,
  stageLabel,
  mcpServerIds,
  onChatMessage,
  sessionId,
}: ChatMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [showScrollBadge, setShowScrollBadge] = useState(false);

  const noopNavigate = useCallback((_docId: string, _blockId: string) => {
    // stub: file-browser.md implements real navigation
  }, []);
  const navigate = navigateToBlock ?? noopNavigate;

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    return el.scrollTop + el.clientHeight >= el.scrollHeight - SCROLL_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
    setShowScrollBadge(false);
  }, []);

  // ResizeObserver: auto-scroll whenever the inner content grows (streaming
  // tokens, new messages, thinking content) without depending on message count.
  useEffect(() => {
    const inner = innerRef.current;
    if (!inner) return;
    const observer = new ResizeObserver(() => {
      if (isNearBottom()) {
        scrollToBottom();
      } else {
        setShowScrollBadge(true);
      }
    });
    observer.observe(inner);
    return () => observer.disconnect();
  }, [isNearBottom, scrollToBottom]);

  const handleScroll = useCallback(() => {
    if (isNearBottom()) setShowScrollBadge(false);
  }, [isNearBottom]);

  // Determine what to render as the last item
  const lastMessage = messages[messages.length - 1];
  const isStreaming =
    isLoading && lastMessage?.role === "assistant" && lastMessage.content.length > 0;
  const isTyping =
    isLoading && (!lastMessage || lastMessage.role !== "assistant" || lastMessage.content.length === 0);

  // Stable messages: all finalised (when streaming, exclude last assistant msg)
  const stableMessages = isStreaming ? messages.slice(0, -1) : messages;

  // Tool calls grouped by parentMessageId for use in MessageBubble.
  // chat-history-deep-fixes-3 / Bug G: when AG-UI emits a tool call without
  // a parentMessageId, attribute it to the most recent assistant message
  // rather than fall back to a shared "__unparented__" key — otherwise
  // every assistant bubble's lookup misses and lands on the same array,
  // and the chip renders inside every prior turn.
  const lastAssistantId = [...stableMessages]
    .reverse()
    .find((m) => m.role === "assistant")?.id;
  const toolCallsByParent = toolCalls.reduce<Record<string, ToolCallState[]>>((acc, tc) => {
    const key = tc.parentMessageId ?? lastAssistantId ?? "__unparented__";
    acc[key] = [...(acc[key] ?? []), tc];
    return acc;
  }, {});

  // Show the most recent running tool name in the TypingIndicator
  const activeToolName = toolCalls.find((tc) => tc.status === "running")?.name ?? null;

  return (
    <div className="relative flex flex-col flex-1 overflow-hidden">
      {activeDocumentContext !== undefined && (
        <ContextBanner context={activeDocumentContext ?? null} />
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        <div ref={innerRef} className="space-y-4 p-4">
          {historyError && (
            <p className="text-xs text-muted-foreground italic">{historyError}</p>
          )}

          {initialMessages && initialMessages.length > 0 && (
            <>
              {initialMessages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  skillId={skillId}
                  userInitial={userInitial}
                  userDisplayName={userDisplayName}
                  toolCalls={[]}
                  navigateToBlock={navigate}
                  onAction={onAction}
                  mcpServerIds={mcpServerIds}
                  onChatMessage={onChatMessage}
                  sessionId={sessionId}
                />
              ))}
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <div className="flex-1 border-t" />
                <span>Earlier in this conversation</span>
                <div className="flex-1 border-t" />
              </div>
            </>
          )}

          {messages.length === 0 && !initialMessages?.length && !error && !isLoading && (
            <APHeroEmpty />
          )}

          {stableMessages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              skillId={skillId}
              userInitial={userInitial}
              userDisplayName={userDisplayName}
              toolCalls={toolCallsByParent[m.id] ?? []}
              navigateToBlock={navigate}
              onAction={onAction}
              mcpServerIds={mcpServerIds}
              onChatMessage={onChatMessage}
              sessionId={sessionId}
            />
          ))}

          {isStreaming && lastMessage && (
            <StreamingBubble
              message={lastMessage}
              skillId={skillId}
              thinkingContent={thinkingContent}
              isThinking={isThinking}
            />
          )}

          {isTyping && (
            <TypingIndicator stageLabel={stageLabel} activeToolName={activeToolName} />
          )}

          {errorBanner && <div className="text-left">{errorBanner}</div>}
        </div>
      </div>

      {showScrollBadge && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-primary/30 bg-background/90 px-3 py-1 text-xs font-medium shadow-lg backdrop-blur hover:bg-muted"
        >
          ↓ New message
        </button>
      )}
    </div>
  );
}

function APHeroEmpty() {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center px-6 py-14 text-center">
      {/* Glowing logo */}
      <div className="relative mb-6">
        <div className="absolute inset-0 scale-[2] rounded-full bg-primary/15 blur-3xl" />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={BRANDING.logo.chatAvatar}
          alt=""
          className="relative h-16 w-16 animate-glow-pulse"
        />
      </div>

      {/* Headlines */}
      <h1 className="gradient-text-gold mb-2 text-2xl font-bold tracking-tight">
        AI-Powered Accounts Payable
      </h1>
      <p className="mb-10 max-w-xs text-sm leading-relaxed text-muted-foreground">
        Multi-agent invoice processing — extract, validate, and post with a complete audit trail.
      </p>

      {/* Pipeline visualization */}
      <div className="mb-10 flex items-center">
        {[
          { label: "Intake", icon: <DocSVG /> },
          { label: "Extract", icon: <SearchSVG /> },
          { label: "Validate", icon: <ShieldSVG /> },
          { label: "Post", icon: <SendSVG /> },
        ].map((step, i) => (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04] text-primary shadow-inner backdrop-blur-sm">
                {step.icon}
              </div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                {step.label}
              </span>
            </div>
            {i < 3 && (
              <div className="mx-2 mb-5 flex items-center gap-0.5">
                <div className="h-px w-4 bg-gradient-to-r from-primary/30 to-primary/5" />
                <div className="h-1 w-1 rounded-full bg-primary/20" />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Try it prompt card */}
      <div className="w-full max-w-sm cursor-default rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 text-left backdrop-blur-sm transition-colors hover:border-primary/25 hover:bg-white/[0.05]">
        <div className="mb-2 flex items-center gap-2">
          <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-primary/80">
            Try an invoice
          </span>
        </div>
        <p className="font-mono text-xs leading-relaxed text-muted-foreground">
          &ldquo;Process: Vendor Acme GmbH (Germany), Invoice INV-2026-042, €8,500, NET 30, GL 5200-OPEX&rdquo;
        </p>
      </div>
    </div>
  );
}

function DocSVG() {
  return (
    <svg className="h-4.5 w-4.5" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M4 1.5h5.5L13 5v9.5H4v-13z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9.5 1.5V5H13" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 8h4M6 10.5h2.5" strokeLinecap="round" />
    </svg>
  );
}

function SearchSVG() {
  return (
    <svg className="h-4.5 w-4.5" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="6.5" cy="6.5" r="4.5" />
      <path d="M10.5 10.5L13.5 13.5" strokeLinecap="round" />
      <path d="M5 6.5h3M6.5 5v3" strokeLinecap="round" />
    </svg>
  );
}

function ShieldSVG() {
  return (
    <svg className="h-4.5 w-4.5" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 1.5L2.5 4v3.5c0 3.5 2.5 5.8 5.5 6.8 3-1 5.5-3.3 5.5-6.8V4L8 1.5z" strokeLinejoin="round" />
      <path d="M5.5 8l1.5 1.5 3-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SendSVG() {
  return (
    <svg className="h-4.5 w-4.5" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M13.5 2.5L1.5 7l5 1.5L8 14l5.5-11.5z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.5 8.5L9 6" strokeLinecap="round" />
    </svg>
  );
}
