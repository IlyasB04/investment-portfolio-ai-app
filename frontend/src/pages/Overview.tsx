import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";
import { usePortfolio } from "../context/PortfolioContext";
import HistoryChart from "./HistoryChart";
import AssistantSlideOver from "../components/AssistantSlideOver";
import styles from "./Overview.module.css";

// ── Types ──────────────────────────────────────────────────────────────────────

interface Transaction {
  id: number;
  ticker: string;
  side: "BUY" | "SELL";
  quantity: string;
  price: string;
  total_value: string;
  created_at: string;
}

// ── Formatters ─────────────────────────────────────────────────────────────────

function fmt(v: string | number | null, dec = 2) {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n)
    ? "—"
    : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ── Allocation Donut (SVG) ─────────────────────────────────────────────────────

const DONUT_COLOURS = [
  "#4F8EFF", "#22D46A", "#F5A623", "#FF4D4F", "#A855F7",
  "#06B6D4", "#F97316", "#10B981", "#EC4899", "#8B5CF6",
];

interface AllocationItem { ticker: string; percent_of_portfolio: string }

function DonutChart({ allocation, size = 148 }: { allocation: AllocationItem[]; size?: number }) {
  const cx = size / 2;
  const cy = size / 2;
  const outerR = size * 0.41;
  const innerR = size * 0.275;
  const gap = 1.6;

  const segments = allocation.slice(0, 8);
  const others   = allocation.slice(8);
  const otherSum = others.reduce((s, a) => s + parseFloat(a.percent_of_portfolio), 0);
  const items    = otherSum > 0
    ? [...segments, { ticker: "Other", percent_of_portfolio: String(otherSum) }]
    : segments;

  let cumAngle = -90;
  const paths: { d: string; colour: string; label: string; pct: number }[] = [];

  items.forEach((item, i) => {
    const pct  = parseFloat(item.percent_of_portfolio);
    const span = (pct / 100) * 360 - gap;
    if (span <= 0) { cumAngle += (pct / 100) * 360; return; }
    const sr = (cumAngle * Math.PI) / 180;
    const er = ((cumAngle + span) * Math.PI) / 180;
    const lg = span > 180 ? 1 : 0;
    const d = [
      `M ${cx + outerR * Math.cos(sr)} ${cy + outerR * Math.sin(sr)}`,
      `A ${outerR} ${outerR} 0 ${lg} 1 ${cx + outerR * Math.cos(er)} ${cy + outerR * Math.sin(er)}`,
      `L ${cx + innerR * Math.cos(er)} ${cy + innerR * Math.sin(er)}`,
      `A ${innerR} ${innerR} 0 ${lg} 0 ${cx + innerR * Math.cos(sr)} ${cy + innerR * Math.sin(sr)} Z`,
    ].join(" ");
    paths.push({ d, colour: DONUT_COLOURS[i % DONUT_COLOURS.length], label: item.ticker, pct });
    cumAngle += (pct / 100) * 360;
  });

  const totalPct = items.reduce((s, a) => s + parseFloat(a.percent_of_portfolio), 0);

  return (
    <div className={styles.donutWrap}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        {paths.length === 0 && (
          <circle cx={cx} cy={cy} r={outerR} fill="none" stroke="var(--border)" strokeWidth={outerR - innerR} />
        )}
        {paths.map((p) => (
          <path key={p.label} d={p.d} fill={p.colour} opacity="0.92">
            <title>{p.label}: {p.pct.toFixed(1)}%</title>
          </path>
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fill="var(--text-primary)" fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
          {totalPct.toFixed(0)}%
        </text>
        <text x={cx} y={cy + 9} textAnchor="middle" fill="var(--text-muted)" fontSize="8" fontFamily="Inter, sans-serif">
          ALLOCATED
        </text>
      </svg>

      <div className={styles.donutLegend}>
        {paths.slice(0, 6).map((p) => (
          <div key={p.label} className={styles.legendItem}>
            <span className={styles.legendDot} style={{ background: p.colour }} />
            <span className={styles.legendTicker}>{p.label}</span>
            <span className={styles.legendPct}>{p.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Overview() {
  const navigate = useNavigate();
  const { summary } = usePortfolio();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [aiOpen, setAiOpen] = useState(false);

  const loadTransactions = useCallback(() => {
    client
      .get<Transaction[]>("/orders/transactions/?limit=6")
      .then((r) => setTransactions(r.data))
      .catch(() => {});
  }, []);

  useEffect(() => { loadTransactions(); }, [loadTransactions]);

  // ── Derived values ──────────────────────────────────────────────────────────

  const topPositions = summary
    ? [...summary.positions]
        .sort((a, b) => parseFloat(b.market_value) - parseFloat(a.market_value))
        .slice(0, 5)
    : [];

  const totalValue    = summary ? parseFloat(summary.total_with_cash) : 0;
  const equitiesValue = summary ? parseFloat(summary.total_value) : 0;
  const cashValue     = summary ? parseFloat(summary.cash_balance) : 0;
  const positionCount = summary?.positions.length ?? 0;

  const totalPnl    = summary
    ? summary.positions.reduce((s, p) => s + parseFloat(p.pnl), 0)
    : null;
  const pnlPositive = totalPnl !== null && totalPnl >= 0;

  const cashRatioPct = totalValue > 0 ? (cashValue / totalValue) * 100 : 100;

  // Diversification label derived from concentration + position count
  const diversLabel = (() => {
    if (!summary || positionCount === 0) return "—";
    const t1 = summary.concentration.top1_percent;
    if (t1 > 55 || positionCount <= 2) return "Concentrated";
    if (t1 > 35 || positionCount <= 4) return "Moderate";
    return "Diversified";
  })();
  const diversColour =
    diversLabel === "Concentrated" ? "var(--negative)"
    : diversLabel === "Moderate"   ? "var(--warning)"
    : "var(--positive)";

  // AI insight text — computed from summary, no extra API call
  const aiInsight = (() => {
    if (!summary || positionCount === 0)
      return "Add positions to unlock AI-powered portfolio analysis and get personalised insights.";
    const t1 = summary.concentration.top1_percent;
    const topTicker = summary.allocation[0]?.ticker;
    if (t1 > 60 && topTicker)
      return `${topTicker} makes up ${t1.toFixed(0)}% of equity. Ask the AI about concentration risk and diversification strategies.`;
    if (totalPnl !== null && totalPnl > 0)
      return `Portfolio is in profit. Ask the AI to analyse top performers and suggest rebalancing opportunities.`;
    if (totalPnl !== null && totalPnl < 0)
      return `Portfolio is down overall. Ask the AI about risk management for your current positions.`;
    return `${positionCount} position${positionCount !== 1 ? "s" : ""} tracked. Ask the AI for strategic insights on allocation, risk, and performance.`;
  })();

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      <div className={styles.dashGrid}>

        {/* ══════════════════════════════════════════════════════════════════════
            ROW 1 — Total Portfolio Value (8 col) + Performance Chart (4 col)
            ══════════════════════════════════════════════════════════════════════ */}

        <div className={`${styles.card} ${styles.heroValueCard}`}>
          {/* Ambient glow decoration */}
          <div className={styles.heroGlow} aria-hidden="true" />

          <div className={styles.hvTop}>
            <span className={styles.hvLabel}>Total Portfolio Value</span>
            <div className={styles.hvAmount}>
              {summary
                ? `$${fmt(summary.total_with_cash)}`
                : <span className={styles.hvPlaceholder}>—</span>}
            </div>

            {totalPnl !== null && (
              <div className={`${styles.hvPnl} ${pnlPositive ? styles.hvPnlPos : styles.hvPnlNeg}`}>
                <span>{pnlPositive ? "▲" : "▼"}</span>
                <span>{pnlPositive ? "+" : ""}${fmt(totalPnl)}</span>
                <span className={styles.hvPnlSep}>·</span>
                <span>Unrealised P&amp;L</span>
              </div>
            )}
          </div>

          <div className={styles.hvStats}>
            <div className={styles.hvStat}>
              <span className={styles.hvStatLabel}>Equities</span>
              <span className={styles.hvStatValue}>${fmt(equitiesValue)}</span>
            </div>
            <div className={styles.hvDivider} />
            <div className={styles.hvStat}>
              <span className={styles.hvStatLabel}>Cash</span>
              <span className={`${styles.hvStatValue} ${styles.cashGreen}`}>${fmt(cashValue)}</span>
            </div>
            <div className={styles.hvDivider} />
            <div className={styles.hvStat}>
              <span className={styles.hvStatLabel}>Positions</span>
              <span className={styles.hvStatValue}>{positionCount}</span>
            </div>
            <div className={styles.hvDivider} />
            <div className={styles.hvStat}>
              <span className={styles.hvStatLabel}>Cash Weight</span>
              <span className={styles.hvStatValue}>{cashRatioPct.toFixed(1)}%</span>
            </div>
          </div>

          <div className={styles.hvActions}>
            <button className={styles.heroPrimaryBtn} onClick={() => navigate("/trade")}>
              <svg viewBox="0 0 16 16" fill="none" width="12" height="12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <path d="M8 2v12M2 8h12" />
              </svg>
              New Order
            </button>
            <button className={styles.heroSecondaryBtn} onClick={() => navigate("/portfolio")}>
              View Portfolio
            </button>
            <button className={styles.heroSecondaryBtn} onClick={() => setAiOpen(true)}>
              <svg viewBox="0 0 16 16" fill="none" width="12" height="12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 8a6 6 0 0 1-6 6H3l-1.5 1.5V8a6 6 0 1 1 12 0z" />
              </svg>
              Ask AI
            </button>
          </div>
        </div>

        {/* ── Performance Chart (4 col) ── */}
        <div className={`${styles.card} ${styles.chartCard}`}>
          <div className={styles.chartCardHeader}>
            <span className={styles.cardLabel}>30-Day Performance</span>
          </div>
          <div className={styles.chartCardBody}>
            <HistoryChart compact />
          </div>
        </div>


        {/* ══════════════════════════════════════════════════════════════════════
            ROW 2 — Top Holdings (8 col) + Allocation (4 col)
            ══════════════════════════════════════════════════════════════════════ */}

        <div className={`${styles.card} ${styles.holdingsCard}`}>
          <div className={styles.cardHeader}>
            <div className={styles.cardTitleGroup}>
              <h2 className={styles.cardTitle}>Top Holdings</h2>
              <span className={styles.cardBadge}>{positionCount}</span>
            </div>
            <button className={styles.linkBtn} onClick={() => navigate("/portfolio")}>
              View all →
            </button>
          </div>

          {topPositions.length === 0 ? (
            <div className={styles.emptyState}>
              <svg viewBox="0 0 40 40" fill="none" width="34" height="34" stroke="var(--text-muted)" strokeWidth="1.2">
                <rect x="4" y="10" width="32" height="24" rx="3" />
                <path d="M12 18h16M12 24h10" />
              </svg>
              <p>No positions yet</p>
              <div className={styles.emptyActions}>
                <button onClick={() => navigate("/import")}>Import CSV</button>
                <button onClick={() => navigate("/trade")}>Place a trade</button>
              </div>
            </div>
          ) : (
            <div className={styles.tableWrap}>
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
                    const pnl    = parseFloat(p.pnl);
                    const mv     = parseFloat(p.market_value);
                    const weight = totalValue > 0 ? (mv / totalValue) * 100 : 0;
                    const pnlPos = pnl >= 0;
                    return (
                      <tr key={p.id} className={styles.tableRow} onClick={() => navigate("/portfolio")}>
                        <td>
                          <div className={styles.tickerCell}>
                            <span className={styles.tickerAvatar}>{p.ticker.slice(0, 2)}</span>
                            <span className={styles.ticker}>{p.ticker}</span>
                            {p.is_synthetic_price && <span className={styles.synthTag}>est</span>}
                          </div>
                        </td>
                        <td className={`${styles.right} ${styles.mono}`}>${fmt(p.price)}</td>
                        <td className={`${styles.right} ${styles.mono}`}>${fmt(p.market_value)}</td>
                        <td className={`${styles.right} ${styles.mono} ${pnlPos ? styles.pos : styles.neg}`}>
                          {pnlPos ? "+" : ""}${fmt(p.pnl)}
                        </td>
                        <td className={styles.right}>
                          <div className={styles.weightCell}>
                            <span className={styles.mono}>{weight.toFixed(1)}%</span>
                            <div className={styles.miniBar}>
                              <div className={styles.miniBarFill} style={{ width: `${Math.min(weight, 100)}%` }} />
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Allocation + Concentration (4 col) ── */}
        <div className={`${styles.card} ${styles.allocationCard}`}>
          {summary && summary.allocation.length > 0 ? (
            <>
              <div className={styles.cardHeader}>
                <h2 className={styles.cardTitle}>Allocation</h2>
              </div>
              <DonutChart allocation={summary.allocation} />

              {/* Concentration divider */}
              <div className={styles.allocDivider} />
              <h3 className={styles.concTitle}>Concentration Risk</h3>
              <div className={styles.concGrid}>
                <div className={styles.concItem}>
                  <div className={styles.concRow}>
                    <span className={styles.concNum}>{summary.concentration.top1_percent.toFixed(1)}%</span>
                    <span className={styles.concLabel}>Top 1</span>
                  </div>
                  <div className={styles.concBar}>
                    <div
                      className={styles.concBarFill}
                      style={{
                        width: `${Math.min(summary.concentration.top1_percent, 100)}%`,
                        background: summary.concentration.top1_percent > 50
                          ? "var(--negative)"
                          : summary.concentration.top1_percent > 30
                          ? "var(--warning)"
                          : "var(--accent)",
                      }}
                    />
                  </div>
                </div>
                <div className={styles.concItem}>
                  <div className={styles.concRow}>
                    <span className={styles.concNum}>{summary.concentration.top3_percent.toFixed(1)}%</span>
                    <span className={styles.concLabel}>Top 3</span>
                  </div>
                  <div className={styles.concBar}>
                    <div
                      className={styles.concBarFill}
                      style={{
                        width: `${Math.min(summary.concentration.top3_percent, 100)}%`,
                        background: summary.concentration.top3_percent > 75
                          ? "var(--negative)"
                          : summary.concentration.top3_percent > 55
                          ? "var(--warning)"
                          : "var(--positive)",
                      }}
                    />
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>
              <p>No allocation data</p>
            </div>
          )}
        </div>


        {/* ══════════════════════════════════════════════════════════════════════
            ROW 3 — Recent Activity (4) + Risk Metrics (4) + AI Panel (4)
            ══════════════════════════════════════════════════════════════════════ */}

        {/* ── Recent Activity (4 col) ── */}
        <div className={`${styles.card} ${styles.activityCard}`}>
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
                  <span className={`${styles.sideBadge} ${t.side === "BUY" ? styles.buyBadge : styles.sellBadge}`}>
                    {t.side}
                  </span>
                  <div className={styles.activityInfo}>
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

        {/* ── Risk Metrics (4 col) ── */}
        <div className={`${styles.card} ${styles.riskCard}`}>
          <h2 className={styles.cardTitle} style={{ marginBottom: "var(--sp-4)" }}>Portfolio Health</h2>

          {/* Diversification score */}
          <div className={styles.riskMetric}>
            <div className={styles.riskMetricHeader}>
              <span className={styles.riskMetricLabel}>Diversification</span>
              <span className={styles.riskMetricBadge} style={{ color: diversColour, borderColor: diversColour, background: `${diversColour}18` }}>
                {diversLabel}
              </span>
            </div>
            <p className={styles.riskMetricSub}>
              {positionCount > 0
                ? `${positionCount} position${positionCount !== 1 ? "s" : ""} · top 1 at ${summary?.concentration.top1_percent.toFixed(1) ?? "—"}%`
                : "No positions"}
            </p>
          </div>

          <div className={styles.riskDivider} />

          {/* Cash ratio */}
          <div className={styles.riskMetric}>
            <div className={styles.riskMetricHeader}>
              <span className={styles.riskMetricLabel}>Cash Ratio</span>
              <span className={styles.riskMetricValue}>{cashRatioPct.toFixed(1)}%</span>
            </div>
            <div className={styles.riskBar}>
              <div
                className={styles.riskBarFill}
                style={{
                  width: `${Math.min(cashRatioPct, 100)}%`,
                  background: cashRatioPct > 60
                    ? "var(--warning)"
                    : cashRatioPct > 30
                    ? "var(--accent)"
                    : "var(--positive)",
                }}
              />
            </div>
            <p className={styles.riskMetricSub}>
              ${fmt(cashValue)} of ${fmt(totalValue)} total
            </p>
          </div>

          <div className={styles.riskDivider} />

          {/* Top 3 weight */}
          <div className={styles.riskMetric}>
            <div className={styles.riskMetricHeader}>
              <span className={styles.riskMetricLabel}>Top 3 Weight</span>
              <span className={styles.riskMetricValue}>{summary?.concentration.top3_percent.toFixed(1) ?? "—"}%</span>
            </div>
            <div className={styles.riskBar}>
              <div
                className={styles.riskBarFill}
                style={{
                  width: `${Math.min(summary?.concentration.top3_percent ?? 0, 100)}%`,
                  background: (summary?.concentration.top3_percent ?? 0) > 75
                    ? "var(--negative)"
                    : (summary?.concentration.top3_percent ?? 0) > 55
                    ? "var(--warning)"
                    : "var(--positive)",
                }}
              />
            </div>
            <p className={styles.riskMetricSub}>% of equity in top 3 positions</p>
          </div>
        </div>

        {/* ── AI Insight Panel (4 col) ── */}
        <button className={styles.aiInsightCard} onClick={() => setAiOpen(true)}>
          <div className={styles.aiGlow} aria-hidden="true" />

          <div className={styles.aiHeader}>
            <div className={styles.aiIconWrap}>
              <svg viewBox="0 0 20 20" fill="none" width="18" height="18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 10a8 8 0 0 1-8 8H4l-2 2V10a8 8 0 1 1 16 0z" />
                <path d="M6.5 10h.01M10 10h.01M13.5 10h.01" strokeWidth="2.4" strokeLinecap="round" />
              </svg>
            </div>
            <span className={styles.aiTitle}>AI Portfolio Assistant</span>
            <span className={styles.aiArrow}>→</span>
          </div>

          <p className={styles.aiInsightText}>{aiInsight}</p>

          <div className={styles.aiCta}>
            <span>Open full assistant</span>
            <svg viewBox="0 0 12 12" fill="none" width="10" height="10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M2 6h8M6 2l4 4-4 4" />
            </svg>
          </div>
        </button>

      </div>{/* /dashGrid */}

      <AssistantSlideOver open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
