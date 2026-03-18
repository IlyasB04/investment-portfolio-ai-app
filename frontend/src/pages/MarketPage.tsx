import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import styles from "./MarketPage.module.css";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Quote {
  ticker: string;
  name: string;
  price: string | null;
  change_pct: number | null;
  source: string;
}

// ── Static instrument lists ───────────────────────────────────────────────────

const TRENDING = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"];
const INDICES   = ["SPY", "QQQ", "IWM", "DIA"];
const ETFS      = ["VTI", "VOO", "ARKK", "GLD", "TLT"];
const TECH      = ["GOOGL", "META", "AMD", "INTC", "NFLX"];

const ALL_TICKERS = [...new Set([...TRENDING, ...INDICES, ...ETFS, ...TECH])];

// ── Ticker avatar colours ─────────────────────────────────────────────────────

const AVATAR_COLOURS = [
  "#4F8EFF","#22D46A","#F5A623","#A855F7","#06B6D4",
  "#F97316","#EC4899","#10B981","#3B82F6","#8B5CF6",
];

function avatarColour(ticker: string): string {
  let h = 0;
  for (let i = 0; i < ticker.length; i++) h = (h * 31 + ticker.charCodeAt(i)) % AVATAR_COLOURS.length;
  return AVATAR_COLOURS[h];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(v: string | number | null, dec = 2) {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

// ── Quote card ────────────────────────────────────────────────────────────────

function QuoteCard({ quote, onTrade }: { quote: Quote; onTrade: (ticker: string, side: "BUY"|"SELL") => void }) {
  const pos = quote.change_pct !== null ? quote.change_pct >= 0 : true;
  const colour = avatarColour(quote.ticker);

  return (
    <div className={styles.quoteCard}>
      <div className={styles.quoteCardTop}>
        <div className={styles.tickerAvatar} style={{ background: `${colour}20`, borderColor: `${colour}40`, color: colour }}>
          {quote.ticker.slice(0, 2)}
        </div>
        <div className={styles.quoteCardMeta}>
          <span className={styles.quoteCardTicker}>{quote.ticker}</span>
          <span className={styles.quoteCardName} title={quote.name ?? ""}>
            {quote.name ?? quote.ticker}
          </span>
        </div>
      </div>

      <div className={styles.quoteCardPrice}>
        {quote.price ? `$${fmt(quote.price)}` : "—"}
      </div>

      {quote.change_pct !== null && (
        <div className={`${styles.quoteCardChange} ${pos ? styles.pos : styles.neg}`}>
          <span>{pos ? "▲" : "▼"}</span>
          <span>{Math.abs(quote.change_pct).toFixed(2)}%</span>
        </div>
      )}

      {quote.source !== "live" && (
        <span className={styles.sourceTag}>{quote.source}</span>
      )}

      <div className={styles.quoteCardActions}>
        <button
          className={styles.buyBtn}
          onClick={() => onTrade(quote.ticker, "BUY")}
        >
          Buy
        </button>
        <button
          className={styles.sellBtn}
          onClick={() => onTrade(quote.ticker, "SELL")}
        >
          Sell
        </button>
      </div>
    </div>
  );
}

// ── Skeleton card ─────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className={styles.quoteCard}>
      <div className={styles.quoteCardTop}>
        <div className={`${styles.tickerAvatar} ${styles.skeletonAvatar}`} />
        <div className={styles.quoteCardMeta}>
          <div className={`${styles.skeletonLine} ${styles.skeletonTicker}`} />
          <div className={`${styles.skeletonLine} ${styles.skeletonName}`} />
        </div>
      </div>
      <div className={`${styles.skeletonLine} ${styles.skeletonPrice}`} />
      <div className={`${styles.skeletonLine} ${styles.skeletonChange}`} />
    </div>
  );
}

// ── Section ───────────────────────────────────────────────────────────────────

function Section({
  title,
  tickers,
  quotes,
  loading,
  onTrade,
}: {
  title: string;
  tickers: string[];
  quotes: Record<string, Quote>;
  loading: boolean;
  onTrade: (ticker: string, side: "BUY"|"SELL") => void;
}) {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      <div className={styles.grid}>
        {tickers.map((t) =>
          loading || !quotes[t] ? (
            <SkeletonCard key={t} />
          ) : (
            <QuoteCard key={t} quote={quotes[t]} onTrade={onTrade} />
          )
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MarketPage() {
  const navigate = useNavigate();
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [searchResult, setSearchResult] = useState<Quote | null>(null);
  const [searching, setSearching] = useState(false);

  const loadQuotes = useCallback(async () => {
    setLoading(true);
    try {
      const results = await Promise.allSettled(
        ALL_TICKERS.map((t) => client.get<Quote>(`/market/quote/${t}/`))
      );
      const map: Record<string, Quote> = {};
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          map[ALL_TICKERS[i]] = r.value.data;
        }
      });
      setQuotes(map);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadQuotes(); }, [loadQuotes]);

  // Debounced search
  useEffect(() => {
    const sym = search.trim().toUpperCase();
    if (sym.length < 1) { setSearchResult(null); return; }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await client.get<Quote>(`/market/quote/${sym}/`);
        setSearchResult(r.data);
      } catch {
        setSearchResult(null);
      } finally {
        setSearching(false);
      }
    }, 380);
    return () => clearTimeout(timer);
  }, [search]);

  function handleTrade(ticker: string, side: "BUY" | "SELL") {
    navigate("/trade", { state: { ticker, side } });
  }

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Market</h1>
          <p className={styles.pageSubtitle}>Discover and trade instruments</p>
        </div>
        <button className={styles.refreshBtn} onClick={loadQuotes} disabled={loading}>
          <svg viewBox="0 0 16 16" fill="none" width="13" height="13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 8a7 7 0 0 1 7-7 7 7 0 0 1 6.3 4M15 8a7 7 0 0 1-7 7 7 7 0 0 1-6.3-4"/>
            <path d="M1 3v4h4M15 13v-4h-4"/>
          </svg>
          Refresh
        </button>
      </div>

      {/* Search */}
      <div className={styles.searchBar}>
        <div className={styles.searchIcon}>
          <svg viewBox="0 0 16 16" fill="none" width="14" height="14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <circle cx="6.5" cy="6.5" r="5"/>
            <path d="M10 10l3.5 3.5"/>
          </svg>
        </div>
        <input
          className={styles.searchInput}
          type="text"
          placeholder="Search ticker symbol… e.g. AAPL"
          value={search}
          onChange={(e) => setSearch(e.target.value.toUpperCase())}
          autoComplete="off"
          spellCheck="false"
        />
        {searching && <span className={styles.searchSpinner} />}
      </div>

      {/* Search result */}
      {search.trim().length > 0 && (
        <div className={styles.searchResults}>
          {searching ? (
            <SkeletonCard />
          ) : searchResult ? (
            <QuoteCard quote={searchResult} onTrade={handleTrade} />
          ) : (
            <div className={styles.noResult}>
              No data found for <strong>{search}</strong>
            </div>
          )}
        </div>
      )}

      {/* Sections */}
      {!search.trim() && (
        <>
          <Section
            title="Trending"
            tickers={TRENDING}
            quotes={quotes}
            loading={loading}
            onTrade={handleTrade}
          />
          <Section
            title="Major Indices"
            tickers={INDICES}
            quotes={quotes}
            loading={loading}
            onTrade={handleTrade}
          />
          <Section
            title="ETFs"
            tickers={ETFS}
            quotes={quotes}
            loading={loading}
            onTrade={handleTrade}
          />
          <Section
            title="Technology"
            tickers={TECH}
            quotes={quotes}
            loading={loading}
            onTrade={handleTrade}
          />
        </>
      )}
    </div>
  );
}
