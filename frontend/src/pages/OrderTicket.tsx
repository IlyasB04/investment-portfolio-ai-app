import { FormEvent, useEffect, useState } from "react";
import axios from "axios";
import client from "../api/client";
import styles from "./OrderTicket.module.css";

interface Quote {
  ticker: string;
  name: string;
  price: string | null;
  change_pct: number | null;
  source: string;
}

interface Props {
  initialTicker?: string;
  initialSide?: "BUY" | "SELL";
  cashBalance: string;
  onClose: () => void;
  onSuccess: () => void;
}

function fmt(v: string | number | null, dec = 2): string {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

export default function OrderTicket({ initialTicker = "", initialSide = "BUY", cashBalance, onClose, onSuccess }: Props) {
  const [side, setSide] = useState<"BUY" | "SELL">(initialSide);
  const [ticker, setTicker] = useState(initialTicker.toUpperCase());
  const [quantity, setQuantity] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Fetch quote whenever ticker changes (debounced)
  useEffect(() => {
    if (ticker.length < 1) { setQuote(null); return; }
    const t = setTimeout(async () => {
      setQuoteLoading(true);
      try {
        const res = await client.get<Quote>(`/market/quote/${ticker}/`);
        setQuote(res.data);
      } catch {
        setQuote(null);
      } finally {
        setQuoteLoading(false);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [ticker]);

  // Escape to close
  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, [onClose]);

  const execPrice = quote?.price ? parseFloat(quote.price) : null;
  const qty = parseFloat(quantity);
  const estimatedValue = execPrice && qty > 0 ? execPrice * qty : null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!ticker) { setError("Enter a ticker."); return; }
    if (!(qty > 0)) { setError("Quantity must be positive."); return; }

    setLoading(true);
    try {
      await client.post("/orders/", { side, ticker, quantity: qty });
      onSuccess();
      onClose();
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.data?.error) {
        setError(err.response.data.error);
      } else {
        setError("Order failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={styles.card} role="dialog" aria-modal="true">
        <div className={styles.cardHeader}>
          <div className={styles.sideToggle}>
            <button className={`${styles.sideBtn} ${side === "BUY" ? styles.buy : ""}`} onClick={() => setSide("BUY")}>Buy</button>
            <button className={`${styles.sideBtn} ${side === "SELL" ? styles.sell : ""}`} onClick={() => setSide("SELL")}>Sell</button>
          </div>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="ot-ticker">Symbol</label>
            <input
              id="ot-ticker"
              className={styles.input}
              type="text"
              placeholder="e.g. AAPL"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              autoFocus
              required
            />
          </div>

          {/* Quote strip */}
          <div className={styles.quoteStrip}>
            {quoteLoading && <span className={styles.quoteLoading}>Fetching quote…</span>}
            {!quoteLoading && quote && quote.price && (
              <>
                <span className={styles.quoteName}>{quote.name}</span>
                <span className={styles.quotePrice}>${fmt(quote.price)}</span>
                {quote.change_pct !== null && (
                  <span className={quote.change_pct >= 0 ? styles.pos : styles.neg}>
                    {quote.change_pct >= 0 ? "+" : ""}{quote.change_pct?.toFixed(2)}%
                  </span>
                )}
                {quote.source !== "live" && <span className={styles.synthetic}>{quote.source}</span>}
              </>
            )}
            {!quoteLoading && ticker && !quote?.price && (
              <span className={styles.quoteLoading}>No quote available — price estimated at execution</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="ot-qty">Quantity</label>
            <input
              id="ot-qty"
              className={styles.input}
              type="number"
              placeholder="0"
              min="0.000001"
              step="any"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
            />
          </div>

          {/* Order summary */}
          <div className={styles.summary}>
            <div className={styles.summaryRow}>
              <span>Est. order value</span>
              <span>{estimatedValue ? `$${fmt(estimatedValue)}` : "—"}</span>
            </div>
            {side === "BUY" && (
              <div className={styles.summaryRow}>
                <span>Cash available</span>
                <span>${fmt(cashBalance)}</span>
              </div>
            )}
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <button type="button" className={styles.cancelBtn} onClick={onClose} disabled={loading}>Cancel</button>
            <button
              type="submit"
              className={`${styles.submitBtn} ${side === "SELL" ? styles.submitSell : ""}`}
              disabled={loading}
            >
              {loading ? "Placing…" : `Place ${side} Order`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
