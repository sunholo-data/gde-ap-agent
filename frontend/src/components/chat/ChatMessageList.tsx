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
            <p className="text-sm text-muted-foreground">
              Send a message to start the conversation.
            </p>
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
          className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-border bg-background px-3 py-1 text-xs font-medium shadow-md hover:bg-muted"
        >
          ↓ New message
        </button>
      )}
    </div>
  );
}
