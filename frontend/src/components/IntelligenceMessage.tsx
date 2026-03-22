/**
 * IntelligenceMessage
 *
 * Shared message bubble component used by both AssistantPage (full layout)
 * and AssistantSlideOver (compact panel).
 *
 * The `compact` prop switches to a condensed rendering:
 *   Full:    all answer sections, full flags panel, full source chips
 *   Compact: direct answer only, inline confidence + intent badge, condensed flags
 *
 * Markdown rendering handles:
 *   **bold**, *italic*, `- bullet lists`, pre-formatted blocks (=== prefix),
 *   and ## section headings.
 */

import { useState } from "react";
import type { IntelligenceMessage as IMsg, ReasoningFlag, IntelligenceSource } from "../context/IntelligenceContext";
import styles from "./IntelligenceMessage.module.css";

// ── SVG icons ─────────────────────────────────────────────────────────────────

export function AssistantIcon({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" width={size} height={size} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 10a8 8 0 0 1-8 8H4l-2 2V10a8 8 0 1 1 16 0z" />
      <path d="M6.5 10h.01M10 10h.01M13.5 10h.01" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

// ── Inline Markdown helpers ────────────────────────────────────────────────────

function RichLine({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**"))
          return <strong key={i}>{part.slice(2, -2)}</strong>;
        if (part.startsWith("*") && part.endsWith("*"))
          return <em key={i}>{part.slice(1, -1)}</em>;
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

function MarkdownBody({ text, preformatted = false }: { text: string; preformatted?: boolean }) {
  if (preformatted) {
    return <pre className={styles.pre}>{text}</pre>;
  }

  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let listBuf: string[] = [];

  function flush() {
    if (!listBuf.length) return;
    nodes.push(
      <ul key={`ul${nodes.length}`} className={styles.mdList}>
        {listBuf.map((item, i) => <li key={i}><RichLine text={item} /></li>)}
      </ul>
    );
    listBuf = [];
  }

  lines.forEach((line, i) => {
    const t = line.trim();
    if (!t) { flush(); return; }
    if (t.startsWith("- ") || t.startsWith("• ")) {
      listBuf.push(t.replace(/^[-•]\s+/, ""));
    } else {
      flush();
      nodes.push(<p key={i} className={styles.mdPara}><RichLine text={t} /></p>);
    }
  });
  flush();
  return <>{nodes}</>;
}

// Splits the answer into named ## sections
interface Section { heading: string; body: string }

function parseSections(text: string): Section[] {
  return text.split(/\n(?=## )/).map((block) => {
    const m = block.match(/^## (.+)/);
    if (!m) return { heading: "", body: block.trim() };
    return { heading: m[1].trim(), body: block.slice(m[0].length).trim() };
  });
}

// ── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({ level }: { level: "high" | "medium" | "low" }) {
  const cls = level === "high" ? styles.confHigh : level === "medium" ? styles.confMed : styles.confLow;
  return <span className={`${styles.confBadge} ${cls}`}>{level.toUpperCase()}</span>;
}

// ── Intent badge ──────────────────────────────────────────────────────────────

const INTENT_LABELS: Record<string, string> = {
  // New intent taxonomy
  portfolio_performance:    "Performance",
  concentration_risk:       "Concentration",
  diversification_strategy: "Diversification",
  macro_impact:             "Macro",
  finance_theory:           "Theory",
  behavioural:              "Behavioural",
  rebalancing_allocation:   "Rebalancing",
  mixed:                    "Mixed",
  // Legacy (backward compat with stored messages)
  portfolio_analysis:       "Portfolio",
  risk_concentration:       "Risk",
  performance_explanation:  "Performance",
};

function IntentBadge({ intent }: { intent: string }) {
  const label = INTENT_LABELS[intent] ?? intent;
  return <span className={styles.intentBadge}>{label}</span>;
}

// ── Reasoning flags ───────────────────────────────────────────────────────────

function FlagsPanel({ flags, compact }: { flags: ReasoningFlag[]; compact: boolean }) {
  const [open, setOpen] = useState(false);
  if (!flags.length) return null;

  return (
    <div className={styles.flagsWrap}>
      <button
        className={styles.flagsToggle}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={styles.flagDot} />
        {flags.length} risk flag{flags.length !== 1 ? "s" : ""}
        <span className={styles.caret}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className={styles.flagsList}>
          {flags.map((f) => {
            const cls = f.severity === "high" ? styles.flagHigh : f.severity === "medium" ? styles.flagMed : styles.flagLow;
            return (
              <div key={f.flag_id} className={`${styles.flagItem} ${cls}`}>
                <div className={styles.flagHeader}>
                  <span className={styles.flagSev}>{f.severity}</span>
                  <span className={styles.flagTitle}>{f.title}</span>
                </div>
                <p className={styles.flagExpl}>{f.explanation}</p>
                {!compact && <p className={styles.flagRec}>→ {f.recommendation}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Sources row ───────────────────────────────────────────────────────────────

function SourcesRow({ sources, compact }: { sources: IntelligenceSource[]; compact: boolean }) {
  if (!sources.length) return null;
  return (
    <div className={styles.sourcesRow}>
      {sources.map((s) => (
        <span
          key={s.citation_label}
          className={styles.sourceChip}
          title={compact ? `${s.title} — ${s.institution}` : undefined}
        >
          {s.citation_label}
          {!compact && <span className={styles.sourceYear}> {s.year}</span>}
        </span>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  msg:     IMsg;
  compact: boolean;
}

export default function IntelligenceMessage({ msg, compact }: Props) {
  if (msg.isError) {
    const isModelDown =
      msg.content.includes("LOCAL_MODEL_UNAVAILABLE") ||
      msg.content.toLowerCase().includes("not running") ||
      msg.content.toLowerCase().includes("start ollama");
    return (
      <div className={`${styles.bubble} ${styles.errorBubble}`}>
        <div className={styles.avatar}><AssistantIcon size={compact ? 12 : 14} /></div>
        <div className={styles.body}>
          {isModelDown ? (
            <p className={styles.errorText}>
              Local intelligence model is not running. Start Ollama with{" "}
              <code className={styles.inlineCode}>ollama run mistral</code> to continue.
            </p>
          ) : (
            <p className={styles.errorText}>{msg.content}</p>
          )}
        </div>
      </div>
    );
  }

  const sections = parseSections(msg.content);

  // In compact mode only show DIRECT ANSWER (first content section after headings)
  const visibleSections = compact
    ? sections.filter((s) => s.heading !== "CONFIDENCE NOTE").slice(0, 2)
    : sections.filter((s) => s.heading !== "CONFIDENCE NOTE");

  return (
    <div className={styles.bubble}>
      <div className={styles.avatar}>
        <AssistantIcon size={compact ? 12 : 14} />
      </div>

      <div className={styles.body}>
        {/* Answer content */}
        <div className={styles.content}>
          {visibleSections.map((sec, i) => {
            if (!sec.heading && !sec.body) return null;
            const isPreBlock =
              sec.heading === "PORTFOLIO CONTEXT" ||
              sec.body.startsWith("===") ||
              sec.body.startsWith("Total:");

            return (
              <div key={i} className={`${styles.section} ${compact ? styles.sectionCompact : ""}`}>
                {sec.heading && !compact && (
                  <div className={styles.sectionHead}>{sec.heading}</div>
                )}
                {sec.heading === "DIRECT ANSWER" && compact && sec.body && (
                  <MarkdownBody text={sec.body} />
                )}
                {(!compact || sec.heading !== "DIRECT ANSWER") && !compact && (
                  <MarkdownBody text={sec.body} preformatted={isPreBlock} />
                )}
                {compact && sec.heading !== "DIRECT ANSWER" && (
                  <MarkdownBody text={sec.body.slice(0, 300) + (sec.body.length > 300 ? "…" : "")} />
                )}
              </div>
            );
          })}
        </div>

        {/* Meta bar */}
        <div className={styles.metaBar}>
          {msg.confidence && <ConfidenceBadge level={msg.confidence} />}
          {msg.intent && <IntentBadge intent={msg.intent} />}
          {msg.modelUsed && (
            <span className={styles.modelTag}>
              {msg.modelUsed === "deterministic-fallback" ? "Deterministic" : msg.modelUsed}
            </span>
          )}
          {msg.retrievalUsed && <span className={styles.ragTag}>RAG</span>}
        </div>

        {/* Flags */}
        {msg.reasoningFlags && msg.reasoningFlags.length > 0 && (
          <FlagsPanel flags={msg.reasoningFlags} compact={compact} />
        )}

        {/* Sources */}
        {msg.sources && msg.sources.length > 0 && (
          <SourcesRow sources={msg.sources} compact={compact} />
        )}
      </div>
    </div>
  );
}
