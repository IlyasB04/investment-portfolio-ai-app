import { useCallback, useEffect, useState } from "react";
import client from "../api/client";
import styles from "./MarketIntelligencePage.module.css";

// ── Types ──────────────────────────────────────────────────────────────────────

type Sentiment = "positive" | "neutral" | "negative";

interface MarketPulse {
  overall_sentiment: Sentiment;
  positive_count:    number;
  neutral_count:     number;
  negative_count:    number;
  top_themes:        string[];
  headline_count:    number;
}

interface Headline {
  source:    string;
  title:     string;
  url:       string;
  published: string | null;
  sentiment: Sentiment;
  themes:    string[];
  tickers:   string[];
}

interface HoldingImpact {
  ticker:      string;
  impact:      Sentiment;
  explanation: string;
}

interface SectorImpact {
  sector:         string;
  impact:         Sentiment;
  headline_count: number;
  explanation:    string;
}

interface IntelligenceData {
  timestamp:       string;
  market_pulse:    MarketPulse;
  headlines:       Headline[];
  holdings_impact: HoldingImpact[];
  sector_impact:   SectorImpact[];
  ai_summary:      string | null;
  ai_error:        string | null;
  sources_used:    string[];
  no_data:         boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function sentimentColour(s: Sentiment): string {
  if (s === "positive") return "var(--positive)";
  if (s === "negative") return "var(--negative)";
  return "var(--text-secondary)";
}

function sentimentLabel(s: Sentiment): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    month:  "short",
    day:    "numeric",
    hour:   "2-digit",
    minute: "2-digit",
  });
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SentimentBadge({ value }: { value: Sentiment }) {
  return (
    <span className={`${styles.badge} ${styles[`badge_${value}`]}`}>
      {sentimentLabel(value)}
    </span>
  );
}

function ThemePill({ label }: { label: string }) {
  return <span className={styles.themePill}>{label}</span>;
}

function ImpactDot({ value }: { value: Sentiment }) {
  return (
    <span
      className={styles.impactDot}
      style={{ background: sentimentColour(value) }}
    />
  );
}

// ── Market Pulse card ──────────────────────────────────────────────────────────

function MarketPulseCard({ pulse }: { pulse: MarketPulse }) {
  const total = pulse.headline_count || 1;
  const posW  = (pulse.positive_count / total) * 100;
  const negW  = (pulse.negative_count / total) * 100;
  const neuW  = 100 - posW - negW;

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>Market Pulse</span>
        <SentimentBadge value={pulse.overall_sentiment} />
      </div>

      {/* Sentiment bar */}
      <div className={styles.sentimentBar} title="Positive / Neutral / Negative">
        <div className={styles.sentimentBarPos} style={{ width: `${posW}%` }} />
        <div className={styles.sentimentBarNeu} style={{ width: `${neuW}%` }} />
        <div className={styles.sentimentBarNeg} style={{ width: `${negW}%` }} />
      </div>

      <div className={styles.pulseStats}>
        <div className={styles.pulseStat}>
          <span className={styles.pulseStatValue} style={{ color: "var(--positive)" }}>
            {pulse.positive_count}
          </span>
          <span className={styles.pulseStatLabel}>Positive</span>
        </div>
        <div className={styles.pulseStat}>
          <span className={styles.pulseStatValue} style={{ color: "var(--text-secondary)" }}>
            {pulse.neutral_count}
          </span>
          <span className={styles.pulseStatLabel}>Neutral</span>
        </div>
        <div className={styles.pulseStat}>
          <span className={styles.pulseStatValue} style={{ color: "var(--negative)" }}>
            {pulse.negative_count}
          </span>
          <span className={styles.pulseStatLabel}>Negative</span>
        </div>
        <div className={styles.pulseStat}>
          <span className={styles.pulseStatValue} style={{ color: "var(--accent)" }}>
            {pulse.headline_count}
          </span>
          <span className={styles.pulseStatLabel}>Headlines</span>
        </div>
      </div>

      {pulse.top_themes.length > 0 && (
        <div className={styles.themeRow}>
          <span className={styles.themeRowLabel}>Top themes</span>
          <div className={styles.themeList}>
            {pulse.top_themes.map((t) => (
              <ThemePill key={t} label={t} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── AI Summary card ────────────────────────────────────────────────────────────

function AiSummaryCard({
  summary,
  error,
}: {
  summary: string | null;
  error:   string | null;
}) {
  return (
    <div className={`${styles.card} ${styles.aiCard}`}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>AI Summary</span>
        <span className={styles.aiBadge}>Groq · llama-3.3-70b</span>
      </div>
      {summary ? (
        <p className={styles.aiText}>{summary}</p>
      ) : (
        <p className={styles.aiUnavailable}>
          {error === "API_NOT_CONFIGURED"
            ? "Groq API key not configured. Add GROQ_API_KEY to your environment."
            : "AI summary unavailable. Headlines are still shown below."}
        </p>
      )}
    </div>
  );
}

// ── Headlines feed ─────────────────────────────────────────────────────────────

function HeadlineCard({ h }: { h: Headline }) {
  return (
    <a
      href={h.url}
      target="_blank"
      rel="noopener noreferrer"
      className={styles.headlineCard}
    >
      <div className={styles.headlineTop}>
        <span className={styles.headlineSource}>{h.source}</span>
        <SentimentBadge value={h.sentiment} />
      </div>
      <p className={styles.headlineTitle}>{h.title}</p>
      <div className={styles.headlineBottom}>
        <span className={styles.headlineTime}>{fmtTime(h.published)}</span>
        {h.themes.length > 0 && (
          <div className={styles.headlineThemes}>
            {h.themes.slice(0, 3).map((t) => (
              <ThemePill key={t} label={t} />
            ))}
          </div>
        )}
        {h.tickers.length > 0 && (
          <div className={styles.headlineTickers}>
            {h.tickers.map((tk) => (
              <span key={tk} className={styles.tickerChip}>{tk}</span>
            ))}
          </div>
        )}
      </div>
    </a>
  );
}

// ── Holdings Impact ────────────────────────────────────────────────────────────

function HoldingsImpactCard({ items }: { items: HoldingImpact[] }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>Holdings Impact</span>
      </div>
      {items.length === 0 ? (
        <p className={styles.emptyMsg}>No holdings in portfolio.</p>
      ) : (
        <div className={styles.impactList}>
          {items.map((item) => (
            <div key={item.ticker} className={styles.impactRow}>
              <div className={styles.impactLeft}>
                <ImpactDot value={item.impact} />
                <span className={styles.impactTicker}>{item.ticker}</span>
                <SentimentBadge value={item.impact} />
              </div>
              <p className={styles.impactExplanation}>{item.explanation}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sector Impact ──────────────────────────────────────────────────────────────

function SectorImpactCard({ items }: { items: SectorImpact[] }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>Sector Exposure</span>
      </div>
      {items.length === 0 ? (
        <p className={styles.emptyMsg}>No sector data available.</p>
      ) : (
        <div className={styles.impactList}>
          {items.map((item) => (
            <div key={item.sector} className={styles.impactRow}>
              <div className={styles.impactLeft}>
                <ImpactDot value={item.impact} />
                <span className={styles.impactTicker}>{item.sector}</span>
                <SentimentBadge value={item.impact} />
                {item.headline_count > 0 && (
                  <span className={styles.headlineCount}>
                    {item.headline_count} hl
                  </span>
                )}
              </div>
              <p className={styles.impactExplanation}>{item.explanation}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Skeleton loader ────────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className={styles.skeletonWrap}>
      <div className={`${styles.skeletonBlock} ${styles.skeletonTall}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonMed}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonMed}`} />
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MarketIntelligencePage() {
  const [data,        setData]        = useState<IntelligenceData | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState("");
  const [headlineTab, setHeadlineTab] = useState<"all" | "positive" | "negative">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await client.get<IntelligenceData>("/market-intelligence/");
      setData(res.data);
    } catch {
      setError("Failed to load market intelligence. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filteredHeadlines = data
    ? headlineTab === "all"
      ? data.headlines
      : data.headlines.filter((h) => h.sentiment === headlineTab)
    : [];

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <h1 className={styles.pageTitle}>Market Intelligence</h1>
          {data && (
            <span className={styles.lastUpdated}>
              Updated {fmtTime(data.timestamp)}
              {data.sources_used.length > 0 && (
                <> · {data.sources_used.join(", ")}</>
              )}
            </span>
          )}
        </div>
        <button
          className={styles.refreshBtn}
          onClick={load}
          disabled={loading}
          title="Refresh market data"
        >
          <RefreshIcon spinning={loading} />
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className={styles.errorBanner}>
          <span>{error}</span>
          <button onClick={load} className={styles.retryBtn}>Retry</button>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !data && <Skeleton />}

      {/* No data warning */}
      {!loading && data?.no_data && (
        <div className={styles.noDataBanner}>
          Unable to fetch live headlines from RSS feeds right now. Market analysis
          may be limited. Try refreshing in a few moments.
        </div>
      )}

      {/* Content */}
      {data && !loading && (
        <>
          {/* Row 1: Pulse + AI summary */}
          <div className={styles.topRow}>
            <MarketPulseCard pulse={data.market_pulse} />
            <AiSummaryCard summary={data.ai_summary} error={data.ai_error} />
          </div>

          {/* Row 2: Holdings Impact + Sector Impact */}
          {(data.holdings_impact.length > 0 || data.sector_impact.length > 0) && (
            <div className={styles.impactRow2}>
              {data.holdings_impact.length > 0 && (
                <HoldingsImpactCard items={data.holdings_impact} />
              )}
              {data.sector_impact.length > 0 && (
                <SectorImpactCard items={data.sector_impact} />
              )}
            </div>
          )}

          {/* Row 3: Headlines feed */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span className={styles.cardTitle}>Headlines Feed</span>
              <div className={styles.tabGroup}>
                {(["all", "positive", "negative"] as const).map((tab) => (
                  <button
                    key={tab}
                    className={`${styles.tab} ${headlineTab === tab ? styles.tabActive : ""}`}
                    onClick={() => setHeadlineTab(tab)}
                  >
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    {tab === "all" && (
                      <span className={styles.tabCount}>{data.headlines.length}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
            {filteredHeadlines.length === 0 ? (
              <p className={styles.emptyMsg}>No headlines in this category.</p>
            ) : (
              <div className={styles.headlineGrid}>
                {filteredHeadlines.map((h, i) => (
                  <HeadlineCard key={`${h.source}-${i}`} h={h} />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      width="15"
      height="15"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={spinning ? { animation: "spin 1s linear infinite" } : undefined}
    >
      <path d="M17 10A7 7 0 1 1 10 3" />
      <path d="M14 3h3v3" />
    </svg>
  );
}
