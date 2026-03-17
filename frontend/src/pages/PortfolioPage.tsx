import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import PortfolioValueChart from "./PortfolioValueChart";
import styles from "./PortfolioPage.module.css";

interface Position {
  id: number;
  ticker: string;
  quantity: string;
  average_cost: string;
  price: string;
  market_value: string;
  pnl: string;
  is_synthetic_price: boolean;
}

interface Allocation {
  ticker: string;
  market_value: string;
  percent_of_portfolio: string;
}

interface Summary {
  total_value: string;
  cash_balance: string;
  total_with_cash: string;
  positions: Position[];
  allocation: Allocation[];
  concentration: { top1_percent: number; top3_percent: number };
}

function fmt(v: string | null, dec = 2) {
  if (v === null) return "—";
  const n = parseFloat(v);
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtPct(v: number | string) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toFixed(2) + "%";
}

export default function PortfolioPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<"market_value" | "pnl" | "ticker">("market_value");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");

  const load = useCallback(() => {
    setLoading(true);
    client
      .get<Summary>("/portfolio/summary/")
      .then((r) => setSummary(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  function toggleSort(col: typeof sortBy) {
    if (sortBy === col) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortBy(col); setSortDir("desc"); }
  }

  const sorted = summary
    ? [...summary.positions].sort((a, b) => {
        let av: number, bv: number;
        if (sortBy === "ticker") return sortDir === "asc" ? a.ticker.localeCompare(b.ticker) : b.ticker.localeCompare(a.ticker);
        av = parseFloat(sortBy === "market_value" ? a.market_value : a.pnl);
        bv = parseFloat(sortBy === "market_value" ? b.market_value : b.pnl);
        return sortDir === "desc" ? bv - av : av - bv;
      })
    : [];

  async function handleDelete(id: number, ticker: string) {
    if (!window.confirm(`Remove ${ticker} from your portfolio? This cannot be undone.`)) return;
    setDeletingId(id);
    setDeleteError(null);
    try {
      await client.delete(`/holdings/${id}/`);
      load();
    } catch {
      setDeleteError("Failed to remove holding. Please try again.");
    } finally {
      setDeletingId(null);
    }
  }

  function sortArrow(col: typeof sortBy) {
    if (sortBy !== col) return <span className={styles.sortNone}>↕</span>;
    return <span className={styles.sortActive}>{sortDir === "desc" ? "↓" : "↑"}</span>;
  }

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
            <p className={styles.bannerValue}>${fmt(summary.total_value)}</p>
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
                      No positions yet. <button className={styles.linkBtn} onClick={() => navigate("/trade")}>Place a trade</button> or <button className={styles.linkBtn} onClick={() => navigate("/import")}>import a CSV</button> to get started.
                    </td>
                  </tr>
                ) : (
                  sorted.map((p) => {
                    const pnl = parseFloat(p.pnl);
                    const cost = parseFloat(p.average_cost);
                    const price = parseFloat(p.price);
                    const pnlPct = cost > 0 ? ((price - cost) / cost) * 100 : 0;
                    return (
                      <tr key={p.id}>
                        <td className={styles.ticker}>{p.ticker}</td>
                        <td className={`${styles.right} ${styles.mono}`}>{fmt(p.quantity, 4)}</td>
                        <td className={`${styles.right} ${styles.mono}`}>${fmt(p.average_cost)}</td>
                        <td className={`${styles.right} ${styles.mono}`}>
                          {p.is_synthetic_price
                            ? <span className={styles.synthPrice}>${fmt(p.price)}</span>
                            : `$${fmt(p.price)}`
                          }
                        </td>
                        <td className={`${styles.right} ${styles.mono}`}>${fmt(p.market_value)}</td>
                        <td className={`${styles.right} ${styles.mono} ${pnl >= 0 ? styles.pos : styles.neg}`}>
                          {pnl >= 0 ? "+" : ""}${fmt(p.pnl)}
                        </td>
                        <td className={`${styles.right} ${styles.mono} ${pnl >= 0 ? styles.pos : styles.neg}`}>
                          {pnl >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                        </td>
                        <td className={styles.actions}>
                          <button className={styles.buyBtn} onClick={() => navigate("/trade", { state: { ticker: p.ticker, side: "BUY" } })}>Buy</button>
                          <button className={styles.sellBtn} onClick={() => navigate("/trade", { state: { ticker: p.ticker, side: "SELL" } })}>Sell</button>
                          <button className={styles.deleteBtn} onClick={() => handleDelete(p.id, p.ticker)} disabled={deletingId === p.id}>
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
                    <div className={styles.barFill} style={{ width: `${Math.min(parseFloat(a.percent_of_portfolio), 100)}%` }} />
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
