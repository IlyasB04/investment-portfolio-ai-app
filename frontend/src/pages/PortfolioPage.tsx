import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { usePortfolio } from "../context/PortfolioContext";
import { useToast } from "../context/ToastContext";
import PortfolioValueChart from "./PortfolioValueChart";
import styles from "./PortfolioPage.module.css";

// ── Formatters ─────────────────────────────────────────────────────────────────

function fmt(v: string | number | null, dec = 2) {
  if (v === null) return "—";
  const n = typeof v === "number" ? v : parseFloat(v);
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtPct(v: number | string) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toFixed(2) + "%";
}

// ── Price-flash hook ───────────────────────────────────────────────────────────
// Compares incoming prices against the previous tick and returns a flash
// direction ("up" | "down") for each ticker that changed.  Flashes clear
// automatically after FLASH_DURATION_MS.

const FLASH_DURATION_MS = 650;

function usePriceFlash(marketPrices: Record<string, number>) {
  const prevRef = useRef<Record<string, number>>({});
  const [flash, setFlash] = useState<Record<string, "up" | "down">>({});

  useEffect(() => {
    if (Object.keys(marketPrices).length === 0) return;

    const next: Record<string, "up" | "down"> = {};
    for (const [ticker, price] of Object.entries(marketPrices)) {
      const prev = prevRef.current[ticker];
      if (prev !== undefined && prev !== price) {
        next[ticker] = price > prev ? "up" : "down";
      }
    }
    // Always keep prev in sync — even if nothing flashed.
    prevRef.current = marketPrices;

    if (Object.keys(next).length === 0) return;

    setFlash(next);
    const t = setTimeout(() => setFlash({}), FLASH_DURATION_MS);
    return () => clearTimeout(t);
  }, [marketPrices]);

  return flash;
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const navigate = useNavigate();
  const { summary, marketPrices, loading, refresh } = usePortfolio();
  const { addToast } = useToast();
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<"market_value" | "pnl" | "ticker">("market_value");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");

  const priceFlash = usePriceFlash(marketPrices);

  function toggleSort(col: typeof sortBy) {
    if (sortBy === col) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortBy(col); setSortDir("desc"); }
  }

  // ── Live total value (updated by marketPrices every 3 s) ─────────────────────
  // Recomputes from live prices so the banner updates without waiting for the
  // full summary refresh.
  const liveTotalEquities = summary
    ? summary.positions.reduce((acc, p) => {
        const livePrice = marketPrices[p.ticker] ?? parseFloat(p.price);
        return acc + livePrice * parseFloat(p.quantity);
      }, 0)
    : null;

  // ── Sorted positions ──────────────────────────────────────────────────────────
  // Sort uses live P&L so the order updates in real time too.
  const sorted = summary
    ? [...summary.positions].sort((a, b) => {
        if (sortBy === "ticker") {
          return sortDir === "asc"
            ? a.ticker.localeCompare(b.ticker)
            : b.ticker.localeCompare(a.ticker);
        }
        const liveA = marketPrices[a.ticker] ?? parseFloat(a.price);
        const liveB = marketPrices[b.ticker] ?? parseFloat(b.price);
        let av: number, bv: number;
        if (sortBy === "market_value") {
          av = liveA * parseFloat(a.quantity);
          bv = liveB * parseFloat(b.quantity);
        } else {
          av = (liveA - parseFloat(a.average_cost)) * parseFloat(a.quantity);
          bv = (liveB - parseFloat(b.average_cost)) * parseFloat(b.quantity);
        }
        return sortDir === "desc" ? bv - av : av - bv;
      })
    : [];

  // ── Delete holding ────────────────────────────────────────────────────────────

  async function handleDelete(id: number, ticker: string) {
    if (!window.confirm(`Remove ${ticker} from your portfolio? This cannot be undone.`)) return;
    setDeletingId(id);
    setDeleteError(null);
    try {
      await client.delete(`/holdings/${id}/`);
      await refresh();
      addToast(`${ticker} removed from portfolio`, "info");
    } catch {
      const msg = "Failed to remove holding. Please try again.";
      setDeleteError(msg);
      addToast(msg, "error");
    } finally {
      setDeletingId(null);
    }
  }

  function sortArrow(col: typeof sortBy) {
    if (sortBy !== col) return <span className={styles.sortNone}>↕</span>;
    return <span className={styles.sortActive}>{sortDir === "desc" ? "↓" : "↑"}</span>;
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Portfolio</h1>
          <p className={styles.pageSubtitle}>Holdings, allocation, and market values</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.secondaryBtn} onClick={() => navigate("/import")}>
            Import CSV
          </button>
          <button className={styles.primaryBtn} onClick={() => navigate("/trade")}>
            + Trade
          </button>
        </div>
      </div>

      {/* ── Summary banner ── */}
      {summary && (
        <div className={styles.banner}>
          <div className={styles.bannerStat}>
            <p className={styles.bannerLabel}>Equities</p>
            <p className={styles.bannerValue}>
              ${liveTotalEquities !== null ? fmt(liveTotalEquities) : fmt(summary.total_value)}
            </p>
          </div>
          <div className={styles.bannerDivider} />
          <div className={styles.bannerStat}>
            <p className={styles.bannerLabel}>Cash</p>
            <p className={styles.bannerValue}>${fmt(summary.cash_balance)}</p>
          </div>
          <div className={styles.bannerDivider} />
          <div className={styles.bannerStat}>
            <p className={styles.bannerLabel}>Top 1 position</p>
            <p className={styles.bannerValue}>{fmtPct(summary.concentration.top1_percent)}</p>
          </div>
          <div className={styles.bannerDivider} />
          <div className={styles.bannerStat}>
            <p className={styles.bannerLabel}>Top 3 positions</p>
            <p className={styles.bannerValue}>{fmtPct(summary.concentration.top3_percent)}</p>
          </div>
        </div>
      )}

      {/* ── Holdings table ── */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>Holdings</h2>
          <span className={styles.count}>{summary?.positions.length ?? 0} positions</span>
        </div>

        {deleteError && <p className={styles.deleteError}>{deleteError}</p>}

        {loading ? (
          <p className={styles.loading}>Loading…</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>
                    <button className={styles.sortBtn} onClick={() => toggleSort("ticker")}>
                      Ticker {sortArrow("ticker")}
                    </button>
                  </th>
                  <th className={styles.right}>Quantity</th>
                  <th className={styles.right}>Avg Cost</th>
                  <th className={styles.right}>Price</th>
                  <th className={styles.right}>
                    <button className={styles.sortBtn} onClick={() => toggleSort("market_value")}>
                      Mkt Value {sortArrow("market_value")}
                    </button>
                  </th>
                  <th className={styles.right}>
                    <button className={styles.sortBtn} onClick={() => toggleSort("pnl")}>
                      P&amp;L {sortArrow("pnl")}
                    </button>
                  </th>
                  <th className={styles.right}>P&amp;L %</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr>
                    <td colSpan={8} className={styles.emptyRow}>
                      No positions yet.{" "}
                      <button className={styles.linkBtn} onClick={() => navigate("/trade")}>
                        Place a trade
                      </button>{" "}
                      or{" "}
                      <button className={styles.linkBtn} onClick={() => navigate("/import")}>
                        import a CSV
                      </button>{" "}
                      to get started.
                    </td>
                  </tr>
                ) : (
                  sorted.map((p) => {
                    // Live price from simulator; fall back to summary price.
                    const livePrice = marketPrices[p.ticker] ?? parseFloat(p.price);
                    const qty = parseFloat(p.quantity);
                    const cost = parseFloat(p.average_cost);
                    const liveMarketValue = livePrice * qty;
                    const livePnl = (livePrice - cost) * qty;
                    const livePnlPct = cost > 0 ? ((livePrice - cost) / cost) * 100 : 0;
                    const flash = priceFlash[p.ticker];

                    return (
                      <tr key={p.id}>
                        <td className={styles.ticker}>{p.ticker}</td>
                        <td className={`${styles.right} ${styles.mono}`}>
                          {fmt(p.quantity, 4)}
                        </td>
                        <td className={`${styles.right} ${styles.mono}`}>
                          ${fmt(p.average_cost)}
                        </td>
                        {/* Price cell — flashes green/red on change */}
                        <td
                          className={[
                            styles.right,
                            styles.mono,
                            flash === "up"
                              ? styles.flashUp
                              : flash === "down"
                              ? styles.flashDown
                              : "",
                          ].join(" ")}
                        >
                          {p.is_synthetic_price && !marketPrices[p.ticker] ? (
                            <span className={styles.synthPrice}>${fmt(livePrice)}</span>
                          ) : (
                            `$${fmt(livePrice)}`
                          )}
                        </td>
                        <td className={`${styles.right} ${styles.mono}`}>
                          ${fmt(liveMarketValue)}
                        </td>
                        <td
                          className={`${styles.right} ${styles.mono} ${livePnl >= 0 ? styles.pos : styles.neg}`}
                        >
                          {livePnl >= 0 ? "+" : ""}${fmt(livePnl)}
                        </td>
                        <td
                          className={`${styles.right} ${styles.mono} ${livePnl >= 0 ? styles.pos : styles.neg}`}
                        >
                          {livePnl >= 0 ? "+" : ""}{livePnlPct.toFixed(2)}%
                        </td>
                        <td className={styles.actions}>
                          <button
                            className={styles.buyBtn}
                            onClick={() => navigate("/trade", { state: { ticker: p.ticker, side: "BUY" } })}
                          >
                            Buy
                          </button>
                          <button
                            className={styles.sellBtn}
                            onClick={() => navigate("/trade", { state: { ticker: p.ticker, side: "SELL" } })}
                          >
                            Sell
                          </button>
                          <button
                            className={styles.deleteBtn}
                            onClick={() => handleDelete(p.id, p.ticker)}
                            disabled={deletingId === p.id}
                          >
                            {deletingId === p.id ? "…" : "Remove"}
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Bottom row: market value chart + allocation ── */}
      {summary && summary.positions.length > 0 && (
        <div className={styles.bottomRow}>
          <PortfolioValueChart positions={summary.positions} />

          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Allocation</h2>
            <div className={styles.allocationList}>
              {summary.allocation.map((a) => (
                <div key={a.ticker} className={styles.allocationRow}>
                  <div className={styles.allocationMeta}>
                    <span className={styles.ticker}>{a.ticker}</span>
                    <span className={styles.allocationPct}>{fmtPct(a.percent_of_portfolio)}</span>
                  </div>
                  <div className={styles.barTrack}>
                    <div
                      className={styles.barFill}
                      style={{ width: `${Math.min(parseFloat(a.percent_of_portfolio), 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
