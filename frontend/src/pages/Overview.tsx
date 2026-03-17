import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { usePortfolio } from "../context/PortfolioContext";
import HistoryChart from "./HistoryChart";
import AssistantSlideOver from "../components/AssistantSlideOver";
import styles from "./Overview.module.css";

interface Transaction {
  id: number;
  ticker: string;
  side: "BUY" | "SELL";
  quantity: string;
  price: string;
  total_value: string;
  created_at: string;
}

function fmt(v: string | number | null, dec = 2) {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function Overview() {
  const navigate = useNavigate();
  // Use global portfolio context — no local summary fetch needed
  const { summary } = usePortfolio();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [aiOpen, setAiOpen] = useState(false);

  const loadTransactions = useCallback(() => {
    client.get<Transaction[]>("/orders/transactions/?limit=5")
      .then((r) => setTransactions(r.data))
      .catch(() => {});
  }, []);

  useEffect(() => { loadTransactions(); }, [loadTransactions]);

  const topPositions = summary
    ? [...summary.positions]
        .sort((a, b) => parseFloat(b.market_value) - parseFloat(a.market_value))
        .slice(0, 5)
    : [];

  const totalValue = summary ? parseFloat(summary.total_with_cash) : 0;

  return (
    <div className={styles.page}>
      {/* ── Page header ── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Overview</h1>
          <p className={styles.pageSubtitle}>Your portfolio at a glance</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.aiBtn} onClick={() => setAiOpen(true)}>
            <span>◆</span> Ask AI
          </button>
          <button className={styles.primaryBtn} onClick={() => navigate("/trade")}>
            + New Order
          </button>
        </div>
      </div>

      {/* ── Metric cards ── */}
      <div className={styles.metrics}>
        <div className={`${styles.metricCard} ${styles.metricCardAccent}`}>
          <p className={styles.metricLabel}>Total Portfolio</p>
          <p className={styles.metricValue}>${fmt(summary?.total_with_cash ?? null)}</p>
        </div>
        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>Equities</p>
          <p className={styles.metricValueSm}>${fmt(summary?.total_value ?? null)}</p>
        </div>
        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>Cash</p>
          <p className={styles.metricValueSm}>${fmt(summary?.cash_balance ?? null)}</p>
        </div>
        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>Positions</p>
          <p className={styles.metricValueSm}>{summary?.positions.length ?? "—"}</p>
        </div>
      </div>

      {/* ── Performance chart ── */}
      <HistoryChart />

      {/* ── Bottom row: top holdings + right column ── */}
      <div className={styles.bottomRow}>
        {/* Top holdings */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Top Holdings</h2>
            <button className={styles.linkBtn} onClick={() => navigate("/portfolio")}>
              View all →
            </button>
          </div>
          {topPositions.length === 0 ? (
            <p className={styles.empty}>No positions yet. <button className={styles.inlineLink} onClick={() => navigate("/import")}>Import a CSV</button> or <button className={styles.inlineLink} onClick={() => navigate("/trade")}>place a trade</button>.</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th className={styles.right}>Price</th>
                  <th className={styles.right}>Mkt Value</th>
                  <th className={styles.right}>P&amp;L</th>
                  <th className={styles.right}>Weight</th>
                </tr>
              </thead>
              <tbody>
                {topPositions.map((p) => {
                  const pnl = parseFloat(p.pnl);
                  const mv = parseFloat(p.market_value);
                  const weight = totalValue > 0 ? (mv / totalValue) * 100 : 0;
                  return (
                    <tr key={p.id}>
                      <td className={styles.ticker}>
                        {p.ticker}
                        {p.is_synthetic_price && <span className={styles.synthTag}>est</span>}
                      </td>
                      <td className={styles.right}>${fmt(p.price)}</td>
                      <td className={styles.right}>${fmt(p.market_value)}</td>
                      <td className={`${styles.right} ${pnl >= 0 ? styles.pos : styles.neg}`}>
                        {pnl >= 0 ? "+" : ""}${fmt(p.pnl)}
                      </td>
                      <td className={styles.right}>{weight.toFixed(1)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Right column */}
        <div className={styles.rightCol}>
          {/* Concentration */}
          {summary && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Concentration</h2>
              <div className={styles.concGrid}>
                <div className={styles.concItem}>
                  <p className={styles.concNum}>{summary.concentration.top1_percent.toFixed(1)}%</p>
                  <p className={styles.concLabel}>Top 1</p>
                </div>
                <div className={styles.concItem}>
                  <p className={styles.concNum}>{summary.concentration.top3_percent.toFixed(1)}%</p>
                  <p className={styles.concLabel}>Top 3</p>
                </div>
              </div>
            </div>
          )}

          {/* Recent activity */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Recent Activity</h2>
              <button className={styles.linkBtn} onClick={() => navigate("/activity")}>
                View all →
              </button>
            </div>
            {transactions.length === 0 ? (
              <p className={styles.empty}>No transactions yet.</p>
            ) : (
              <div className={styles.activityList}>
                {transactions.map((t) => (
                  <div key={t.id} className={styles.activityRow}>
                    <div className={styles.activityLeft}>
                      <span className={`${styles.sideBadge} ${t.side === "BUY" ? styles.buyBadge : styles.sellBadge}`}>
                        {t.side}
                      </span>
                      <span className={styles.activityTicker}>{t.ticker}</span>
                      <span className={styles.activityQty}>{fmt(t.quantity, 4)} sh</span>
                    </div>
                    <div className={styles.activityRight}>
                      <span className={styles.activityValue}>${fmt(t.total_value)}</span>
                      <span className={styles.activityDate}>{fmtDate(t.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* AI launcher card */}
          <div className={`${styles.card} ${styles.aiCard}`} onClick={() => setAiOpen(true)}>
            <span className={styles.aiCardIcon}>◆</span>
            <div>
              <p className={styles.aiCardTitle}>AI Portfolio Assistant</p>
              <p className={styles.aiCardSub}>Ask about your holdings, P&amp;L, concentration, and more</p>
            </div>
            <span className={styles.aiCardArrow}>→</span>
          </div>
        </div>
      </div>

      {/* ── AI Slide-over ── */}
      <AssistantSlideOver open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
