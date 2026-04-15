/**
 * AssistantPage — full-width portfolio intelligence console at /assistant
 *
 * Layout: two-column
 *   Left  — conversation sidebar (new chat + scrollable history list)
 *   Right — active chat area (messages + input + model status banner)
 *
 * State is entirely owned by IntelligenceContext. This component contains
 * zero request logic, zero session storage logic, and zero duplicated state.
 */

import { type FormEvent, useEffect, useRef, useState } from "react";
import { useIntelligence } from "../context/IntelligenceContext";
import IntelligenceMessage, { AssistantIcon } from "../components/IntelligenceMessage";
import styles from "./AssistantPage.module.css";

// ── SVG icons ──────────────────────────────────────────────────────────────────

function SendIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 2L2 9l7 3 3 7 6-17z" />
      <path d="M9 12l4-4" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="13" height="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M10 4v12M4 10h12" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="13" height="13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 10a8 8 0 0 1-8 8H4l-2 2V10a8 8 0 1 1 16 0z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="11" height="11" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h14M8 6V4h4v2M16 6l-1 11H5L4 6" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="7" r="4" />
      <path d="M2 18c0-4 3.6-7 8-7s8 3 8 7" />
    </svg>
  );
}

// ── Suggested prompts ──────────────────────────────────────────────────────────

const SUGGESTED = [
  "Analyse my portfolio concentration risk",
  "Which positions are my biggest losers?",
  "How would rising interest rates affect my holdings?",
  "Explain diversification strategy for my allocation",
  "What does modern portfolio theory say about my portfolio?",
  "Am I holding too much cash?",
];

// ── Relative time helper ───────────────────────────────────────────────────────

function relativeTime(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)  return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Page component ─────────────────────────────────────────────────────────────

export default function AssistantPage() {
  const {
    conversations,
    conversationsLoaded,
    activeConversationId,
    messages,
    messagesLoaded,
    loading,
    modelAvailable,
    createConversation,
    loadConversation,
    deleteConversation,
    sendMessage,
    checkModelStatus,
  } = useIntelligence();

  const inputRef  = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when conversation changes
  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [activeConversationId]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const val = inputRef.current?.value.trim() ?? "";
    if (!val || loading) return;
    if (inputRef.current) inputRef.current.value = "";
    void sendMessage(val);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as FormEvent);
    }
  }

  async function handleNewChat() {
    await createConversation();
    setTimeout(() => inputRef.current?.focus(), 100);
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    setDeletingId(id);
    await deleteConversation(id);
    setDeletingId(null);
  }

  const isInputDisabled = loading || modelAvailable === false;

  return (
    <div className={styles.page}>

      {/* ── Left sidebar ── */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <button className={styles.newChatBtn} onClick={handleNewChat}>
            <PlusIcon />
            New Chat
          </button>
        </div>

        <div className={styles.convList}>
          {!conversationsLoaded && (
            <div className={styles.convLoading}>
              <span /><span /><span />
            </div>
          )}

          {conversationsLoaded && conversations.length === 0 && (
            <p className={styles.convEmpty}>No conversations yet</p>
          )}

          {conversations.map((conv) => (
            <button
              key={conv.id}
              className={`${styles.convItem} ${conv.id === activeConversationId ? styles.convItemActive : ""}`}
              onClick={() => void loadConversation(conv.id)}
              title={conv.lastQuestion || conv.title}
            >
              <span className={styles.convItemIcon}><ChatIcon /></span>
              <span className={styles.convItemBody}>
                <span className={styles.convItemTitle}>{conv.title}</span>
                <span className={styles.convItemMeta}>
                  {relativeTime(conv.updatedAt)}
                  {conv.messageCount > 0 && (
                    <span className={styles.convItemCount}>{conv.messageCount}</span>
                  )}
                </span>
              </span>
              <button
                className={`${styles.convDeleteBtn} ${deletingId === conv.id ? styles.convDeleteBtnActive : ""}`}
                onClick={(e) => void handleDelete(e, conv.id)}
                title="Delete conversation"
                aria-label="Delete"
              >
                <TrashIcon />
              </button>
            </button>
          ))}
        </div>

        <div className={styles.sidebarFooter}>
          <div className={`${styles.modelStatus} ${
            modelAvailable === true  ? styles.modelOnline  :
            modelAvailable === false ? styles.modelOffline :
            styles.modelChecking
          }`}>
            <span className={styles.modelDot} />
            <span className={styles.modelLabel}>
              {modelAvailable === true  ? "Assistant · ready" :
               modelAvailable === false ? "API unavailable"  :
               "Checking…"}
            </span>
            {modelAvailable === false && (
              <button className={styles.retryBtn} onClick={() => void checkModelStatus()}>
                Retry
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main chat area ── */}
      <main className={styles.chatMain}>

        {/* Model unavailable banner */}
        {modelAvailable === false && (
          <div className={styles.unavailableBanner}>
            <span className={styles.unavailableIcon}>⚠</span>
            <span>
              Assistant is unavailable. Check that{" "}
              <strong>ANTHROPIC_API_KEY</strong> is set in the backend environment.
            </span>
            <button className={styles.bannerRetry} onClick={() => void checkModelStatus()}>
              Check again
            </button>
          </div>
        )}

        {/* Message list */}
        <div className={styles.messages}>

          {/* Loading history skeleton */}
          {!messagesLoaded && (
            <div className={styles.historyLoading}>
              <span className={styles.loadingDot} />
              <span className={styles.loadingDot} />
              <span className={styles.loadingDot} />
            </div>
          )}

          {/* Empty state */}
          {messagesLoaded && messages.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}><AssistantIcon size={28} /></div>
              <p className={styles.emptyTitle}>Portfolio Intelligence</p>
              <p className={styles.emptySub}>
                Local AI · intent routing · RAG retrieval · deterministic risk analysis
              </p>
              {modelAvailable !== false && (
                <div className={styles.suggestions}>
                  {SUGGESTED.map((q) => (
                    <button
                      key={q}
                      className={styles.suggestion}
                      onClick={() => void sendMessage(q)}
                      disabled={loading}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Conversation turns */}
          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <div key={i} className={`${styles.message} ${styles.userMsg}`}>
                <div className={styles.msgAvatar}><UserIcon /></div>
                <div className={styles.msgBody}>
                  <p className={styles.userContent}>{msg.content}</p>
                </div>
              </div>
            ) : (
              <IntelligenceMessage key={i} msg={msg} compact={false} />
            )
          )}

          {/* Typing indicator */}
          {loading && (
            <div className={styles.typingWrap}>
              <div className={styles.typingAvatar}><AssistantIcon size={14} /></div>
              <div className={styles.typing}><span /><span /><span /></div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className={styles.inputArea}>
          <textarea
            ref={inputRef}
            className={styles.input}
            placeholder={
              modelAvailable === false
                ? "Assistant unavailable…"
                : "Ask about your portfolio… (Enter to send, Shift+Enter for newline)"
            }
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={isInputDisabled}
            aria-label="Chat input"
          />
          <button
            type="submit"
            className={styles.sendBtn}
            disabled={isInputDisabled}
            aria-label="Send message"
          >
            <SendIcon />
          </button>
        </form>
      </main>
    </div>
  );
}
