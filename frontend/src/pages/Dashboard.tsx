import { useCallback, useEffect, useState } from "react";
import client from "../api/client";
import { useAuth } from "../context/AuthContext";
import PortfolioValueChart from "./PortfolioValueChart";
import HistoryChart from "./HistoryChart";
import OrderTicket from "./OrderTicket";
import InstrumentSearch from "./InstrumentSearch";
import styles from "./Dashboard.module.css";

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

interface Concentration {
  top1_percent: number;
  top3_percent: number;
}

interface Summary {
  total_value: string;
  cash_balance: string;
  total_with_cash: string;
  positions: Position[];
  allocation: Allocation[];
  concentration: Concentration;
}

interface Transaction {
  id: number;
  ticker: string;
  side: "BUY" | "SELL";
  quantity: string;
  price: string;
  total_value: string;
  cash_after: string;
  created_at: string;
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

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function Dashboard() {
  const { logout } = useAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [orderTicket, setOrderTicket] = useState<{ open: boolean; ticker: string; side: "BUY" | "SELL" }>({
    open: false,
    ticker: "",
    side: "BUY",
  });
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadSummary = useCallback(() => {
    client
      .get<Summary>("/portfolio/summary/")
      .then((res) => setSummary(res.data))
      .catch(() => setError("Failed to load portfolio data."));
  }, []);

  const loadTransactions = useCallback(() => {
    client
      .get<Transaction[]>("/orders/transactions/")
      .then((res) => setTransactions(res.data))
      .catch(() => {/* silently fail */});
  }, []);

  useEffect(() => {
    loadSummary();
    loadTransactions();
  }, [loadSummary, loadTransactions]);

  function handleRefresh() {
    loadSummary();
    loadTransactions();
  }

  function openOrderTicket(ticker: string, side: "BUY" | "SELL") {
    setOrderTicket({ open: true, ticker, side });
  }

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
      {orderTicket.open && summary && (
        <OrderTicket
          initialTicker={orderTicket.ticker}
          initialSide={orderTicket.side}
          cashBalance={summary.cash_balance}
          onClose={() => setOrderTicket((s) => ({ ...s, open: false }))}
          onSuccess={handleRefresh}
        />
      )}

      <header className={styles.topbar}>
        <span className={styles.brand}>◈ Portfolio</span>
        <InstrumentSearch onTrade={openOrderTicket} />
        <div className={styles.topbarRight}>
          <button
            className={styles.tradeBtn}
            onClick={() => openOrderTicket("", "BUY")}
          >
            + Trade
          </button>
          <button className={styles.logout} onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <main className={styles.main}>
        {error && <p className={styles.error}>{error}</p>}

        {!summary && !error && (
          <p className={styles.loading}>Loading…</p>
        )}

        {summary && (
          <>
            {/* Hero */}
            <section className={styles.hero}>
              <div className={styles.heroLeft}>
                <div className={styles.heroBlock}>
                  <p className={styles.heroLabel}>Total Portfolio</p>
                  <p className={styles.heroValue}>${fmt(summary.total_with_cash)}</p>
                </div>
                <div className={styles.heroDivider} />
                <div className={styles.heroBlock}>
                  <p className={styles.heroLabel}>Equities</p>
                  <p className={styles.heroValueSm}>${fmt(summary.total_value)}</p>
                </div>
                <div className={styles.heroBlock}>
                  <p className={styles.heroLabel}>Cash</p>
                  <p className={styles.heroValueSm}>${fmt(summary.cash_balance)}</p>
                </div>
              </div>
              <button
                className={styles.addTradeBtn}
                onClick={() => openOrderTicket("", "BUY")}
              >
                + New Order
              </button>
            </section>

            {/* Performance chart */}
            <HistoryChart />

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
                          <span className={p.is_synthetic_price ? styles.synthetic : undefined}>
                            ${fmt(p.price)}
                          </span>
                        </td>
                        <td className={styles.right}>${fmt(p.market_value)}</td>
                        <td className={`${styles.right} ${pnlClass(p.pnl)}`}>
                          {parseFloat(p.pnl) >= 0 ? "+" : ""}${fmt(p.pnl)}
                        </td>
                        <td className={styles.actionCell}>
                          <div className={styles.rowActions}>
                            <button
                              className={styles.buyBtn}
                              onClick={() => openOrderTicket(p.ticker, "BUY")}
                            >
                              Buy
                            </button>
                            <button
                              className={styles.sellBtn}
                              onClick={() => openOrderTicket(p.ticker, "SELL")}
                            >
                              Sell
                            </button>
                            <button
                              className={styles.deleteBtn}
                              onClick={() => handleDelete(p.id, p.ticker)}
                              disabled={deletingId === p.id}
                            >
                              {deletingId === p.id ? "…" : "Delete"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Portfolio Value Chart */}
            <PortfolioValueChart positions={summary.positions} />

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

            {/* Recent Transactions */}
            {transactions.length > 0 && (
              <section className={styles.section}>
                <h2 className={styles.sectionTitle}>Recent Activity</h2>
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Ticker</th>
                        <th>Side</th>
                        <th className={styles.right}>Qty</th>
                        <th className={styles.right}>Price</th>
                        <th className={styles.right}>Total</th>
                        <th className={styles.right}>Cash After</th>
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map((t) => (
                        <tr key={t.id}>
                          <td>{fmtDate(t.created_at)}</td>
                          <td className={styles.ticker}>{t.ticker}</td>
                          <td className={t.side === "BUY" ? styles.positive : styles.negative}>
                            {t.side}
                          </td>
                          <td className={styles.right}>{fmt(t.quantity, 4)}</td>
                          <td className={styles.right}>${fmt(t.price)}</td>
                          <td className={styles.right}>${fmt(t.total_value)}</td>
                          <td className={styles.right}>${fmt(t.cash_after)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
