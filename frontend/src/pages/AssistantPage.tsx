import { FormEvent, useEffect, useRef, useState } from "react";
import client from "../api/client";
import styles from "./AssistantPage.module.css";

interface Message {
  role: "user" | "assistant";
  content: string;
  contextSummary?: string;
}

const SUGGESTED = [
  "What is my largest holding?",
  "Which positions are currently down?",
  "How concentrated is my portfolio?",
  "How much cash do I have left?",
  "Summarise my portfolio risk in simple terms",
  "What changed in my portfolio recently?",
];

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setLoading(true);
    try {
      const res = await client.post<{ response: string; context_summary: string }>("/ai/chat/", { message: q });
      setMessages((prev) => [...prev, { role: "assistant", content: res.data.response, contextSummary: res.data.context_summary }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, I couldn't reach the assistant. Please try again." }]);
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
    <div className={styles.page}>
      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}><span className={styles.titleIcon}>◆</span> AI Assistant</h1>
          <p className={styles.pageSubtitle}>Grounded on your real portfolio — holdings, P&amp;L, cash, and activity</p>
        </div>
        <span className={styles.badge}>Portfolio-aware</span>
      </div>

      {/* ── Chat layout ── */}
      <div className={styles.chatWrap}>
        {/* Sidebar: context & suggestions */}
        <div className={styles.sidebar}>
          <div className={styles.sideCard}>
            <h3 className={styles.sideTitle}>What I can access</h3>
            <ul className={styles.contextList}>
              <li>Your current holdings</li>
              <li>Quantities &amp; average costs</li>
              <li>Live or estimated prices</li>
              <li>Unrealised P&amp;L</li>
              <li>Allocation &amp; concentration</li>
              <li>Cash balance</li>
              <li>Recent transactions</li>
            </ul>
          </div>

          <div className={styles.sideCard}>
            <h3 className={styles.sideTitle}>Try asking</h3>
            <div className={styles.suggestions}>
              {SUGGESTED.map((q) => (
                <button
                  key={q}
                  className={styles.suggestion}
                  onClick={() => send(q)}
                  disabled={loading}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Main chat */}
        <div className={styles.chatMain}>
          <div className={styles.messages}>
            {messages.length === 0 && (
              <div className={styles.emptyState}>
                <span className={styles.emptyIcon}>◆</span>
                <p className={styles.emptyTitle}>Ask about your portfolio</p>
                <p className={styles.emptySub}>I have access to your live portfolio data. Try one of the suggestions on the left or ask your own question.</p>
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

          <form onSubmit={handleSubmit} className={styles.inputArea}>
            <textarea
              ref={inputRef}
              className={styles.input}
              placeholder="Ask about your portfolio…  (Enter to send, Shift+Enter for new line)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={loading}
            />
            <button type="submit" className={styles.sendBtn} disabled={!input.trim() || loading}>
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
