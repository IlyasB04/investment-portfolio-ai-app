/**
 * AssistantSlideOver — compact intelligence panel, slide-over from any page.
 *
 * Consumes IntelligenceContext exclusively — the same conversation list,
 * active conversation, and loading state as the full /assistant page.
 * Opening this panel mid-session on Overview shows the current conversation.
 * Navigating to /assistant after closing shows the same thread.
 *
 * Shows a model unavailable state if Ollama is not running.
 */

import { type FormEvent, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useIntelligence } from "../context/IntelligenceContext";
import IntelligenceMessage, { AssistantIcon } from "./IntelligenceMessage";
import styles from "./AssistantSlideOver.module.css";

// ── Icons ──────────────────────────────────────────────────────────────────────

function UserIcon({ size = 12 }: { size?: number }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" width={size} height={size} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="7" r="4" />
      <path d="M2 18c0-4 3.6-7 8-7s8 3 8 7" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 2L2 9l7 3 3 7 6-17z" />
      <path d="M9 12l4-4" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" width="11" height="11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 3H3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V9" />
      <path d="M10 2h4v4M14 2L8 8" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="11" height="11" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <path d="M10 4v12M4 10h12" />
    </svg>
  );
}

// ── Suggested prompts (compact set) ───────────────────────────────────────────

const SUGGESTED = [
  "How concentrated is my portfolio?",
  "Which positions are losing?",
  "Is my cash ratio too high?",
  "Summarise my portfolio risk",
];

// ── Component ──────────────────────────────────────────────────────────────────

interface Props {
  open:    boolean;
  onClose: () => void;
}

export default function AssistantSlideOver({ open, onClose }: Props) {
  const navigate = useNavigate();
  const {
    messages,
    loading,
    messagesLoaded,
    activeConversationId,
    modelAvailable,
    sendMessage,
    createConversation,
    clearConversation,
    checkModelStatus,
  } = useIntelligence();

  const inputRef  = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 130);
  }, [open]);

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

  function goFullView() {
    onClose();
    navigate("/assistant");
  }

  async function handleNewChat() {
    await createConversation();
    setTimeout(() => inputRef.current?.focus(), 100);
  }

  const isInputDisabled = loading || modelAvailable === false;

  return (
    <>
      {/* Backdrop */}
      <div
        className={`${styles.backdrop} ${open ? styles.backdropVisible : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className={`${styles.panel} ${open ? styles.panelOpen : ""}`}
        role="dialog"
        aria-label="Portfolio Intelligence"
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>
              <AssistantIcon size={12} />
            </span>
            <h2 className={styles.title}>Intelligence</h2>
            <span className={styles.badge}>Local AI</span>
          </div>
          <div className={styles.headerRight}>
            <button
              className={styles.newChatBtn}
              onClick={() => void handleNewChat()}
              title="New conversation"
              aria-label="New chat"
            >
              <PlusIcon />
            </button>
            <button
              className={styles.fullViewBtn}
              onClick={goFullView}
              title="Open full intelligence console"
              aria-label="Open full view"
            >
              <ExternalLinkIcon />
            </button>
            <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        {/* Model unavailable notice */}
        {modelAvailable === false && (
          <div className={styles.modelBanner}>
            <span>⚠ Assistant unavailable —</span>
            <span>check API key configuration</span>
            <button className={styles.bannerRetry} onClick={() => void checkModelStatus()}>
              Retry
            </button>
          </div>
        )}

        {/* Messages */}
        <div className={styles.messages}>

          {/* History loading */}
          {!messagesLoaded && (
            <div className={styles.historyLoading}>
              <span /><span /><span />
            </div>
          )}

          {/* Empty state */}
          {messagesLoaded && messages.length === 0 && (
            <div className={styles.empty}>
              <p className={styles.emptyTitle}>Ask about your portfolio</p>
              <p className={styles.emptySubtitle}>
                Intent-routed, evidence-grounded analysis from your live holdings.
              </p>
              {modelAvailable !== false && (
                <div className={styles.suggestions}>
                  {SUGGESTED.map((q) => (
                    <button
                      key={q}
                      className={styles.suggestion}
                      onClick={() => { void sendMessage(q); }}
                      disabled={loading}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Conversation */}
          {messages.map((msg, i) =>
            msg.role === "user" ? (
              <div key={i} className={`${styles.message} ${styles.userMsg}`}>
                <div className={styles.msgIcon}><UserIcon size={11} /></div>
                <p className={styles.userContent}>{msg.content}</p>
              </div>
            ) : (
              <IntelligenceMessage key={i} msg={msg} compact={true} />
            )
          )}

          {/* Typing indicator */}
          {loading && (
            <div className={styles.message}>
              <div className={styles.msgIcon}>
                <AssistantIcon size={12} />
              </div>
              <div className={styles.typing}><span /><span /><span /></div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Session bar */}
        {(activeConversationId !== null || messages.length > 0) && (
          <div className={styles.sessionBar}>
            {activeConversationId !== null && (
              <span className={styles.sessionLabel} title={activeConversationId}>
                {messages.length} message{messages.length !== 1 ? "s" : ""}
              </span>
            )}
            {messages.length > 0 && (
              <button className={styles.clearSmall} onClick={clearConversation}>
                Close
              </button>
            )}
          </div>
        )}

        {/* Input */}
        <form onSubmit={handleSubmit} className={styles.inputArea}>
          <textarea
            ref={inputRef}
            className={styles.input}
            placeholder={
              modelAvailable === false
                ? "Assistant unavailable…"
                : "Ask about your portfolio…"
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
            aria-label="Send"
          >
            <SendIcon />
          </button>
        </form>
      </div>
    </>
  );
}
