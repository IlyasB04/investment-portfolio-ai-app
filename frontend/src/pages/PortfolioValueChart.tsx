import styles from "./PortfolioValueChart.module.css";

interface Position {
  id: number;
  ticker: string;
  market_value: string;
}

interface ChartRow {
  id: number;
  ticker: string;
  market_value: number;
  widthPct: number;  // relative to largest bar (largest = 100%)
  sharePct: number;  // share of total priced value
}

interface Props {
  positions: Position[];
}

function fmtValue(n: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function PortfolioValueChart({ positions }: Props) {
  const priced = positions
    .map((p) => ({ id: p.id, ticker: p.ticker, market_value: parseFloat(p.market_value) }))
    .filter((p) => p.market_value > 0)
    .sort((a, b) => b.market_value - a.market_value);

  if (priced.length === 0) return null;

  const maxValue = priced[0].market_value;
  const total = priced.reduce((sum, p) => sum + p.market_value, 0);

  const rows: ChartRow[] = priced.map((p) => ({
    ...p,
    widthPct: (p.market_value / maxValue) * 100,
    sharePct: (p.market_value / total) * 100,
  }));

  return (
    <section className={styles.section}>
      <h2 className={styles.title}>Market Value</h2>
      <div className={styles.chart}>
        {rows.map((row) => (
          <div key={row.id} className={styles.row}>
            <span className={styles.label}>{row.ticker}</span>
            <div className={styles.barTrack}>
              <div
                className={styles.bar}
                style={{ width: `${row.widthPct}%` }}
              >
                <span className={styles.barPct}>
                  {row.sharePct.toFixed(1)}%
                </span>
              </div>
            </div>
            <span className={styles.value}>${fmtValue(row.market_value)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
