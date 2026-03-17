import { FormEvent, useEffect, useRef, useState } from "react";
import client from "../api/client";
import styles from "./AssistantSlideOver.module.css";

interface Message {
  role: "user" | "assistant";
  content: string;
  contextSummary?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

const SUGGESTED = [
  "What is my largest holding?",
  "Which positions are down?",
  "How much cash do I have?",
  "Summarise my portfolio risk",
];

export default function AssistantSlideOver({ open, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 120);
  }, [open]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setLoading(true);
    try {
      const res = await client.post<{ response: string; context_summary: string }>("/ai/chat/", { message: q });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.data.response, contextSummary: res.data.context_summary },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I couldn't reach the assistant. Please try again." },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleSubmit(e: FormEvent) { e.preventDefault(); send(input); }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className={`${styles.backdrop} ${open ? styles.backdropVisible : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className={`${styles.panel} ${open ? styles.panelOpen : ""}`} role="dialog" aria-label="AI Assistant">
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>◆</span>
            <h2 className={styles.title}>AI Assistant</h2>
            <span className={styles.badge}>Portfolio-aware</span>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Messages */}
        <div className={styles.messages}>
          {messages.length === 0 && (
            <div className={styles.empty}>
              <p className={styles.emptyTitle}>Ask about your portfolio</p>
              <p className={styles.emptySubtitle}>
                The assistant has live access to your holdings, P&amp;L, cash, and recent transactions.
              </p>
              <div className={styles.suggestions}>
                {SUGGESTED.map((q) => (
                  <button key={q} className={styles.suggestion} onClick={() => send(q)} disabled={loading}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`${styles.message} ${msg.role === "user" ? styles.userMsg : styles.assistantMsg}`}>
              {msg.role === "assistant" && <span className={styles.msgIcon}>◆</span>}
              <div className={styles.msgBody}>
                <p className={styles.msgContent}>{msg.content}</p>
                {msg.contextSummary && <p className={styles.msgMeta}>{msg.contextSummary}</p>}
              </div>
            </div>
          ))}

          {loading && (
            <div className={`${styles.message} ${styles.assistantMsg}`}>
              <span className={styles.msgIcon}>◆</span>
              <div className={styles.typing}>
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSubmit} className={styles.inputArea}>
          <textarea
            ref={inputRef}
            className={styles.input}
            placeholder="Ask about your portfolio…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={loading}
          />
          <button type="submit" className={styles.sendBtn} disabled={!input.trim() || loading}>
            Ask
          </button>
        </form>
      </div>
    </>
  );
}
