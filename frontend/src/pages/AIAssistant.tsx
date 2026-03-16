import { FormEvent, useEffect, useRef, useState } from "react";
import client from "../api/client";
import styles from "./AIAssistant.module.css";

interface Message {
  role: "user" | "assistant";
  content: string;
  contextSummary?: string;
}

const SUGGESTED_QUESTIONS = [
  "What is my largest holding?",
  "Which positions are down?",
  "How concentrated is my portfolio?",
  "Summarise my recent activity",
  "How much cash do I have?",
];

export default function AIAssistant() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await client.post<{ response: string; context_summary: string }>(
        "/ai/chat/",
        { message: question }
      );
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.data.response,
          contextSummary: res.data.context_summary,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I couldn't reach the assistant. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.headerIcon}>◆</span>
          <h2 className={styles.title}>AI Assistant</h2>
        </div>
        <span className={styles.badge}>Portfolio-aware</span>
      </div>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>Ask about your portfolio</p>
            <p className={styles.emptySubtitle}>
              The assistant has access to your live holdings, P&amp;L, cash balance,
              and recent transactions.
            </p>
            <div className={styles.suggestions}>
              {SUGGESTED_QUESTIONS.map((q) => (
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
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`${styles.message} ${
              msg.role === "user" ? styles.userMessage : styles.assistantMessage
            }`}
          >
            {msg.role === "assistant" && (
              <span className={styles.msgIcon}>◆</span>
            )}
            <div className={styles.msgBody}>
              <p className={styles.msgContent}>{msg.content}</p>
              {msg.contextSummary && (
                <p className={styles.msgMeta}>{msg.contextSummary}</p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className={`${styles.message} ${styles.assistantMessage}`}>
            <span className={styles.msgIcon}>◆</span>
            <div className={styles.msgBody}>
              <div className={styles.typing}>
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

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
        <button
          type="submit"
          className={styles.sendBtn}
          disabled={!input.trim() || loading}
        >
          Ask
        </button>
      </form>
    </section>
  );
}
