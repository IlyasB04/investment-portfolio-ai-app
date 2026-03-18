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

// ── Allocation Donut Chart (SVG) ──────────────────────────────────────────────

const DONUT_COLOURS = [
  "#4F8EFF", "#22D46A", "#F5A623", "#FF4D4F", "#A855F7",
  "#06B6D4", "#F97316", "#10B981", "#EC4899", "#8B5CF6",
];

interface AllocationItem { ticker: string; percent_of_portfolio: string; }

function DonutChart({ allocation }: { allocation: AllocationItem[] }) {
  const size = 160;
  const cx = size / 2;
  const cy = size / 2;
  const outerR = 66;
  const innerR = 44;
  const gap = 1.8; // degrees between segments

  const segments = allocation.slice(0, 8);
  const others = allocation.slice(8);
  const othersTotal = others.reduce((s, a) => s + parseFloat(a.percent_of_portfolio), 0);

  const items = othersTotal > 0
    ? [...segments, { ticker: "Other", percent_of_portfolio: String(othersTotal) }]
    : segments;

  let cumAngle = -90; // start at top
  const paths: Array<{ d: string; colour: string; label: string; pct: number }> = [];

  items.forEach((item, i) => {
    const pct = parseFloat(item.percent_of_portfolio);
    const span = (pct / 100) * 360 - gap;
    if (span <= 0) { cumAngle += (pct / 100) * 360; return; }

    const startRad = (cumAngle * Math.PI) / 180;
    const endRad   = ((cumAngle + span) * Math.PI) / 180;

    const x1 = cx + outerR * Math.cos(startRad);
    const y1 = cy + outerR * Math.sin(startRad);
    const x2 = cx + outerR * Math.cos(endRad);
    const y2 = cy + outerR * Math.sin(endRad);
    const x3 = cx + innerR * Math.cos(endRad);
    const y3 = cy + innerR * Math.sin(endRad);
    const x4 = cx + innerR * Math.cos(startRad);
    const y4 = cy + innerR * Math.sin(startRad);
    const lg = span > 180 ? 1 : 0;

    const d = `M ${x1} ${y1} A ${outerR} ${outerR} 0 ${lg} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerR} ${innerR} 0 ${lg} 0 ${x4} ${y4} Z`;
    paths.push({ d, colour: DONUT_COLOURS[i % DONUT_COLOURS.length], label: item.ticker, pct });
    cumAngle += (pct / 100) * 360;
  });

  const totalPct = items.reduce((s, a) => s + parseFloat(a.percent_of_portfolio), 0);

  return (
    <div className={styles.donutWrap}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        {paths.length === 0 && (
          <circle cx={cx} cy={cy} r={outerR} fill="none" stroke="var(--border)" strokeWidth={outerR - innerR}/>
        )}
        {paths.map((p) => (
          <path key={p.label} d={p.d} fill={p.colour} opacity="0.9">
            <title>{p.label}: {p.pct.toFixed(1)}%</title>
          </path>
        ))}
        {/* Center label */}
        <text x={cx} y={cy - 7} textAnchor="middle" fill="var(--text-primary)" fontSize="14" fontWeight="700" fontFamily="Inter, sans-serif">
          {totalPct.toFixed(0)}%
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fill="var(--text-muted)" fontSize="9" fontFamily="Inter, sans-serif">
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

// ── Main Component ────────────────────────────────────────────────────────────

export default function Overview() {
  const navigate = useNavigate();
  const { summary } = usePortfolio();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [aiOpen, setAiOpen] = useState(false);

  const loadTransactions = useCallback(() => {
    client.get<Transaction[]>("/orders/transactions/?limit=6")
      .then((r) => setTransactions(r.data))
      .catch(() => {});
  }, []);

  useEffect(() => { loadTransactions(); }, [loadTransactions]);

  const topPositions = summary
    ? [...summary.positions]
        .sort((a, b) => parseFloat(b.market_value) - parseFloat(a.market_value))
        .slice(0, 5)
    : [];

  const totalValue     = summary ? parseFloat(summary.total_with_cash) : 0;
  const equitiesValue  = summary ? parseFloat(summary.total_value) : 0;
  const cashValue      = summary ? parseFloat(summary.cash_balance) : 0;
  const positionCount  = summary?.positions.length ?? 0;

  // Compute total unrealised P&L from positions
  const totalPnl = summary
    ? summary.positions.reduce((s, p) => s + parseFloat(p.pnl), 0)
    : null;
  const pnlPositive = totalPnl !== null && totalPnl >= 0;

  return (
    <div className={styles.page}>

      {/* ══ HERO ZONE ════════════════════════════════════════════════════════ */}
      <div className={styles.heroSection}>
        <div className={styles.heroCard}>
          {/* Left: value + stats */}
          <div className={styles.heroLeft}>
            <div className={styles.heroLabel}>Total Portfolio Value</div>
            <div className={styles.heroValue}>
              ${summary ? fmt(summary.total_with_cash) : <span className={styles.heroPlaceholder}>—</span>}
            </div>

            {totalPnl !== null && (
              <div className={`${styles.heroPnl} ${pnlPositive ? styles.heroPnlPos : styles.heroPnlNeg}`}>
                <span className={styles.heroPnlIcon}>{pnlPositive ? "▲" : "▼"}</span>
                <span>{pnlPositive ? "+" : ""}${fmt(totalPnl)}</span>
                <span className={styles.heroPnlSep}>·</span>
                <span>Unrealised P&amp;L</span>
              </div>
            )}

            <div className={styles.heroMeta}>
              <div className={styles.heroMetaItem}>
                <span className={styles.heroMetaLabel}>Equities</span>
                <span className={styles.heroMetaValue}>${fmt(equitiesValue)}</span>
              </div>
              <div className={styles.heroMetaDivider}/>
              <div className={styles.heroMetaItem}>
                <span className={styles.heroMetaLabel}>Cash</span>
                <span className={`${styles.heroMetaValue} ${styles.cashGreen}`}>${fmt(cashValue)}</span>
              </div>
              <div className={styles.heroMetaDivider}/>
              <div className={styles.heroMetaItem}>
                <span className={styles.heroMetaLabel}>Positions</span>
                <span className={styles.heroMetaValue}>{positionCount}</span>
              </div>
            </div>

            <div className={styles.heroActions}>
              <button className={styles.heroPrimaryBtn} onClick={() => navigate("/trade")}>
                <svg viewBox="0 0 16 16" fill="none" width="13" height="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M8 2v12M2 8h12"/>
                </svg>
                New Order
              </button>
              <button className={styles.heroSecondaryBtn} onClick={() => setAiOpen(true)}>
                <svg viewBox="0 0 16 16" fill="none" width="13" height="13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 8a6 6 0 0 1-6 6H3l-1.5 1.5V8a6 6 0 1 1 12 0z"/>
                </svg>
                Ask AI
              </button>
            </div>
          </div>

          {/* Right: sparkline chart */}
          <div className={styles.heroRight}>
            <div className={styles.heroChartLabel}>30-Day Performance</div>
            <HistoryChart compact />
          </div>
        </div>
      </div>

      {/* ══ MAIN GRID ════════════════════════════════════════════════════════ */}
      <div className={styles.mainGrid}>

        {/* ── Top Holdings ── */}
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
              <svg viewBox="0 0 40 40" fill="none" width="36" height="36" stroke="var(--text-muted)" strokeWidth="1.2">
                <rect x="4" y="10" width="32" height="24" rx="3"/>
                <path d="M12 18h16M12 24h10"/>
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
                      <tr
                        key={p.id}
                        className={styles.tableRow}
                        onClick={() => navigate("/portfolio")}
                      >
                        <td>
                          <div className={styles.tickerCell}>
                            <span className={styles.tickerAvatar}>
                              {p.ticker.slice(0, 2)}
                            </span>
                            <span className={styles.ticker}>{p.ticker}</span>
                            {p.is_synthetic_price && (
                              <span className={styles.synthTag}>est</span>
                            )}
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
                              <div
                                className={styles.miniBarFill}
                                style={{ width: `${Math.min(weight, 100)}%` }}
                              />
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

        {/* ── Right column ── */}
        <div className={styles.rightCol}>

          {/* Allocation Donut */}
          {summary && summary.allocation.length > 0 && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <h2 className={styles.cardTitle}>Allocation</h2>
              </div>
              <DonutChart allocation={summary.allocation} />
            </div>
          )}

          {/* Concentration card */}
          {summary && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Concentration Risk</h2>
              <div className={styles.concGrid}>
                <div className={styles.concItem}>
                  <p className={styles.concNum}>{summary.concentration.top1_percent.toFixed(1)}%</p>
                  <p className={styles.concLabel}>Top 1 position</p>
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
                  <p className={styles.concNum}>{summary.concentration.top3_percent.toFixed(1)}%</p>
                  <p className={styles.concLabel}>Top 3 positions</p>
                  <div className={styles.concBar}>
                    <div
                      className={styles.concBarFill}
                      style={{
                        width: `${Math.min(summary.concentration.top3_percent, 100)}%`,
                        background: summary.concentration.top3_percent > 75
                          ? "var(--negative)"
                          : summary.concentration.top3_percent > 60
                          ? "var(--warning)"
                          : "var(--positive)",
                      }}
                    />
                  </div>
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

          {/* AI launcher card */}
          <button
            className={styles.aiCard}
            onClick={() => setAiOpen(true)}
          >
            <div className={styles.aiCardGlow} />
            <div className={styles.aiCardIcon}>
              <svg viewBox="0 0 20 20" fill="none" width="20" height="20" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 10a8 8 0 0 1-8 8H4l-2 2V10a8 8 0 1 1 16 0z"/>
                <path d="M6.5 10h.01M10 10h.01M13.5 10h.01" strokeWidth="2.4" strokeLinecap="round"/>
              </svg>
            </div>
            <div className={styles.aiCardText}>
              <p className={styles.aiCardTitle}>AI Portfolio Assistant</p>
              <p className={styles.aiCardSub}>Ask about your holdings, P&amp;L, and risk</p>
            </div>
            <div className={styles.aiCardArrow}>→</div>
          </button>
        </div>
      </div>

      {/* ── AI Slide-over ── */}
      <AssistantSlideOver open={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  );
}
