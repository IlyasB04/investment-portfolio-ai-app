import { useNavigate } from "react-router-dom";
import InstrumentSearch from "../pages/InstrumentSearch";
import { usePortfolio } from "../context/PortfolioContext";
import styles from "./TopBar.module.css";

function fmt(v: string | null) {
  if (!v) return "—";
  const n = parseFloat(v);
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Props {
  onQuickTrade?: (ticker: string, side: "BUY" | "SELL") => void;
}

export default function TopBar({ onQuickTrade }: Props) {
  const navigate = useNavigate();
  const { summary } = usePortfolio();

  function handleTrade(ticker: string, side: "BUY" | "SELL") {
    if (onQuickTrade) {
      onQuickTrade(ticker, side);
    } else {
      navigate("/trade", { state: { ticker, side } });
    }
  }

  const portfolioValue = summary?.total_with_cash ?? null;
  const equitiesValue  = summary?.total_value ?? null;
  const cashValue      = summary?.cash_balance ?? null;

  return (
    <header className={styles.topbar}>
      {/* Left: instrument search */}
      <div className={styles.searchWrap}>
        <InstrumentSearch onTrade={handleTrade} />
      </div>

      {/* Centre: portfolio stats strip */}
      {summary && (
        <div className={styles.statsStrip}>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Total</span>
            <span className={styles.statValue}>${fmt(portfolioValue)}</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.stat}>
            <span className={styles.statLabel}>Equities</span>
            <span className={styles.statValue}>${fmt(equitiesValue)}</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.stat}>
            <span className={styles.statLabel}>Cash</span>
            <span className={`${styles.statValue} ${styles.cashValue}`}>${fmt(cashValue)}</span>
          </div>
        </div>
      )}

      {/* Right: actions */}
      <div className={styles.actions}>
        <button
          className={styles.tradeBtn}
          onClick={() => navigate("/trade")}
          aria-label="Open trade page"
        >
          <svg viewBox="0 0 16 16" fill="none" width="13" height="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M8 2v12M2 8h12"/>
          </svg>
          Trade
        </button>
      </div>
    </header>
  );
}
