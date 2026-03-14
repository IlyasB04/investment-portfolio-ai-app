import { useCallback, useEffect, useState } from "react";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import TradeModal from "./TradeModal";
import styles from "./Dashboard.module.css";

interface Position {
  id: number;
  ticker: string;
  quantity: string;
  average_cost: string;
  price: string | null;
  market_value: string | null;
  pnl: string | null;
}

interface Allocation {
  ticker: string;
  market_value: string;
  percent_of_portfolio: string;
}

interface Concentration {
  top1_percent: number;
  top3_percent: number;
}

interface Summary {
  total_value: string;
  positions: Position[];
  allocation: Allocation[];
  concentration: Concentration;
}

function fmt(value: string | null, decimals = 2): string {
  if (value === null) return "—";
  const n = parseFloat(value);
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(value: number | string): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return isNaN(n) ? "—" : n.toFixed(2) + "%";
}

function pnlClass(value: string | null): string {
  if (value === null) return "";
  const n = parseFloat(value);
  if (n > 0) return styles.positive;
  if (n < 0) return styles.negative;
  return "";
}

export default function Dashboard() {
  const { logout } = useAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadSummary = useCallback(() => {
    client
      .get<Summary>("/portfolio/summary/")
      .then((res) => setSummary(res.data))
      .catch(() => setError("Failed to load portfolio data."));
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  async function handleDelete(id: number, ticker: string) {
    if (!window.confirm(`Delete holding ${ticker}? This cannot be undone.`)) return;
    setDeletingId(id);
    setDeleteError(null);
    try {
      await client.delete(`/holdings/${id}/`);
      loadSummary();
    } catch {
      setDeleteError("Failed to delete holding. Please try again.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={styles.page}>
      {modalOpen && (
        <TradeModal
          onClose={() => setModalOpen(false)}
          onSuccess={loadSummary}
        />
      )}
      <header className={styles.topbar}>
        <span className={styles.brand}>◈ Portfolio</span>
        <button className={styles.logout} onClick={logout}>
          Sign out
        </button>
      </header>

      <main className={styles.main}>
        {error && <p className={styles.error}>{error}</p>}

        {!summary && !error && (
          <p className={styles.loading}>Loading…</p>
        )}

        {summary && (
          <>
            {/* Total value */}
            <section className={styles.hero}>
              <div>
                <p className={styles.heroLabel}>Total Portfolio Value</p>
                <p className={styles.heroValue}>${fmt(summary.total_value)}</p>
              </div>
              <button
                className={styles.addTradeBtn}
                onClick={() => setModalOpen(true)}
              >
                + Add Trade
              </button>
            </section>

            {/* Positions */}
            <section className={styles.section}>
              <h2 className={styles.sectionTitle}>Positions</h2>
              {deleteError && <p className={styles.deleteError}>{deleteError}</p>}
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th className={styles.right}>Qty</th>
                      <th className={styles.right}>Avg Cost</th>
                      <th className={styles.right}>Price</th>
                      <th className={styles.right}>Market Value</th>
                      <th className={styles.right}>P&amp;L</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.positions.map((p) => (
                      <tr key={p.id}>
                        <td className={styles.ticker}>{p.ticker}</td>
                        <td className={styles.right}>{fmt(p.quantity, 4)}</td>
                        <td className={styles.right}>${fmt(p.average_cost)}</td>
                        <td className={styles.right}>
                          {p.price ? `$${fmt(p.price)}` : "—"}
                        </td>
                        <td className={styles.right}>
                          {p.market_value ? `$${fmt(p.market_value)}` : "—"}
                        </td>
                        <td className={`${styles.right} ${pnlClass(p.pnl)}`}>
                          {p.pnl
                            ? `${parseFloat(p.pnl) >= 0 ? "+" : ""}$${fmt(p.pnl)}`
                            : "—"}
                        </td>
                        <td className={styles.actionCell}>
                          <button
                            className={styles.deleteBtn}
                            onClick={() => handleDelete(p.id, p.ticker)}
                            disabled={deletingId === p.id}
                          >
                            {deletingId === p.id ? "…" : "Delete"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Allocation + Concentration */}
            <div className={styles.row}>
              <section className={styles.section}>
                <h2 className={styles.sectionTitle}>Allocation</h2>
                <div className={styles.allocationList}>
                  {summary.allocation.map((a) => (
                    <div key={a.ticker} className={styles.allocationRow}>
                      <div className={styles.allocationMeta}>
                        <span className={styles.ticker}>{a.ticker}</span>
                        <span className={styles.allocationPct}>
                          {fmtPct(a.percent_of_portfolio)}
                        </span>
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
              </section>

              <section className={styles.section}>
                <h2 className={styles.sectionTitle}>Concentration</h2>
                <div className={styles.concGrid}>
                  <div className={styles.concCard}>
                    <p className={styles.concLabel}>Top 1 holding</p>
                    <p className={styles.concValue}>
                      {fmtPct(summary.concentration.top1_percent)}
                    </p>
                  </div>
                  <div className={styles.concCard}>
                    <p className={styles.concLabel}>Top 3 holdings</p>
                    <p className={styles.concValue}>
                      {fmtPct(summary.concentration.top3_percent)}
                    </p>
                  </div>
                </div>
              </section>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
