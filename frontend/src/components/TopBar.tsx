import { useNavigate } from "react-router-dom";
import InstrumentSearch from "../pages/InstrumentSearch";
import styles from "./TopBar.module.css";

interface Props {
  onQuickTrade?: (ticker: string, side: "BUY" | "SELL") => void;
}

export default function TopBar({ onQuickTrade }: Props) {
  const navigate = useNavigate();

  function handleTrade(ticker: string, side: "BUY" | "SELL") {
    if (onQuickTrade) {
      onQuickTrade(ticker, side);
    } else {
      // Navigate to trade page with state
      navigate("/trade", { state: { ticker, side } });
    }
  }

  return (
    <header className={styles.topbar}>
      <div className={styles.searchWrap}>
        <InstrumentSearch onTrade={handleTrade} />
      </div>

      <div className={styles.actions}>
        <button
          className={styles.tradeBtn}
          onClick={() => navigate("/trade")}
        >
          + Trade
        </button>
      </div>
    </header>
  );
}
