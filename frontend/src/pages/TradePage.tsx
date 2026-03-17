import { FormEvent, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import axios from "axios";
import client from "../api/client";
import { usePortfolio } from "../context/PortfolioContext";
import { useToast } from "../context/ToastContext";
import styles from "./TradePage.module.css";

interface Quote {
  ticker: string;
  name: string;
  price: string | null;
  change_pct: number | null;
  source: string;
}

interface Holding {
  id: number;
  ticker: string;
  quantity: string;
  average_cost: string;
}

interface OrderResult {
  status: string;
  side: string;
  ticker: string;
  quantity: string;
  executed_price: string;
  total_value: string;
  cash_balance: string;
  price_source: string;
}

function fmt(v: string | number | null, dec = 2) {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

export default function TradePage() {
  const location = useLocation();
  const state = location.state as { ticker?: string; side?: "BUY" | "SELL" } | null;
  const { summary, refresh: refreshPortfolio } = usePortfolio();
  const { addToast } = useToast();

  const [side, setSide] = useState<"BUY" | "SELL">(state?.side ?? "BUY");
  const [ticker, setTicker] = useState((state?.ticker ?? "").toUpperCase());
  const [quantity, setQuantity] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [holding, setHolding] = useState<Holding | null>(null);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OrderResult | null>(null);
  const quantityRef = useRef<HTMLInputElement>(null);

  // Cash balance comes from the global portfolio context — always up to date
  const cashBalance = summary?.cash_balance ?? null;

  // Fetch quote + current holding whenever ticker changes (debounced 380ms)
  useEffect(() => {
    if (ticker.length < 1) { setQuote(null); setHolding(null); return; }
    const timer = setTimeout(async () => {
      setQuoteLoading(true);
      try {
        const [quoteRes, holdingsRes] = await Promise.all([
          client.get<Quote>(`/market/quote/${ticker}/`),
          client.get<Holding[]>("/holdings/"),
        ]);
        setQuote(quoteRes.data);
        const found = holdingsRes.data.find((h) => h.ticker.toUpperCase() === ticker);
        setHolding(found ?? null);
      } catch {
        setQuote(null);
        setHolding(null);
      } finally {
        setQuoteLoading(false);
      }
    }, 380);
    return () => clearTimeout(timer);
  }, [ticker]);

  const execPrice = quote?.price ? parseFloat(quote.price) : null;
  const qty = parseFloat(quantity);
  const estimatedValue = execPrice && qty > 0 ? execPrice * qty : null;
  const cashNum = cashBalance ? parseFloat(cashBalance) : null;
  const willExceedCash = side === "BUY" && estimatedValue !== null && cashNum !== null && estimatedValue > cashNum;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (!ticker) { setError("Enter a ticker symbol."); return; }
    if (!(qty > 0)) { setError("Quantity must be greater than zero."); return; }

    setExecuting(true);
    try {
      const res = await client.post<OrderResult>("/orders/", { side, ticker, quantity: qty });
      setResult(res.data);
      setQuantity("");

      // Refresh global portfolio — updates cash, Overview metrics, PortfolioPage
      await refreshPortfolio();

      // Refresh local holding display
      const holdingsRes = await client.get<Holding[]>("/holdings/");
      const found = holdingsRes.data.find((h) => h.ticker.toUpperCase() === ticker);
      setHolding(found ?? null);

      // Success toast
      const filled = res.data;
      addToast(
        `${filled.side} ${fmt(filled.quantity, 4)} ${filled.ticker} @ $${fmt(filled.executed_price)} · Total $${fmt(filled.total_value)}`,
        "success",
        5000,
      );

      setTimeout(() => quantityRef.current?.focus(), 80);

    } catch (err) {
      let msg = "Order failed. Please try again.";
      if (axios.isAxiosError(err) && err.response?.data?.error) {
        msg = err.response.data.error;
      }
      setError(msg);
      addToast(msg, "error");
    } finally {
      setExecuting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Trade</h1>
        <p className={styles.pageSubtitle}>Paper trading — no real money involved</p>
      </div>

      <div className={styles.layout}>
        {/* ── Left: Quote panel ── */}
        <div className={styles.quotePanel}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Quote</h2>

            <div className={styles.tickerField}>
              <label className={styles.fieldLabel}>Symbol</label>
              <input
                className={styles.tickerInput}
                type="text"
                placeholder="e.g. AAPL"
                value={ticker}
                onChange={(e) => {
                  setTicker(e.target.value.toUpperCase());
                  setResult(null);
                  setError(null);
                }}
                autoFocus
              />
            </div>

            {quoteLoading && (
              <div className={styles.quoteSkeleton}>
                <div className={styles.skeletonLine} />
                <div className={styles.skeletonPrice} />
                <div className={styles.skeletonLine} style={{ width: "45%" }} />
              </div>
            )}

            {!quoteLoading && quote && (
              <div className={styles.quoteData}>
                <p className={styles.quoteName}>{quote.name}</p>
                {quote.price ? (
                  <>
                    <p className={styles.quotePrice}>${fmt(quote.price)}</p>
                    {quote.change_pct !== null && (
                      <p className={quote.change_pct >= 0 ? styles.pos : styles.neg}>
                        {quote.change_pct >= 0 ? "▲" : "▼"} {Math.abs(quote.change_pct).toFixed(2)}% today
                      </p>
                    )}
                    {quote.source !== "live" && (
                      <span className={styles.sourceTag}>{quote.source} price</span>
                    )}
                  </>
                ) : (
                  <p className={styles.quoteUnavailable}>
                    Price unavailable — execution price set at order time
                  </p>
                )}
              </div>
            )}

            {!quoteLoading && !quote && ticker && (
              <p className={styles.quoteLoading}>Enter a valid ticker to see the quote</p>
            )}

            {/* Current holding */}
            {holding && (
              <div className={styles.holdingCard}>
                <p className={styles.holdingLabel}>Your position</p>
                <div className={styles.holdingRow}>
                  <span>Shares held</span>
                  <span className={styles.holdingVal}>{fmt(holding.quantity, 4)}</span>
                </div>
                <div className={styles.holdingRow}>
                  <span>Avg cost</span>
                  <span className={styles.holdingVal}>${fmt(holding.average_cost)}</span>
                </div>
                {execPrice !== null && (
                  <div className={styles.holdingRow}>
                    <span>Unrealised P&amp;L</span>
                    <span className={`${styles.holdingVal} ${(execPrice - parseFloat(holding.average_cost)) >= 0 ? styles.posVal : styles.negVal}`}>
                      {(execPrice - parseFloat(holding.average_cost)) >= 0 ? "+" : ""}$
                      {fmt((execPrice - parseFloat(holding.average_cost)) * parseFloat(holding.quantity))}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Cash balance from global store */}
            {cashBalance && (
              <div className={styles.cashCard}>
                <p className={styles.holdingLabel}>Available cash</p>
                <p className={styles.cashValue}>${fmt(cashBalance)}</p>
              </div>
            )}
          </div>
        </div>

        {/* ── Right: Order form ── */}
        <div className={styles.orderPanel}>
          <div className={styles.card}>
            {/* Result banner */}
            {result && (
              <div className={styles.successBanner}>
                <span className={styles.successIcon}>✓</span>
                <div>
                  <p className={styles.successTitle}>Order filled</p>
                  <p className={styles.successDetail}>
                    {result.side} {fmt(result.quantity, 4)} {result.ticker} @ ${fmt(result.executed_price)}
                    {" · "}Total ${fmt(result.total_value)}
                    {result.price_source !== "live" && ` · ${result.price_source} price`}
                  </p>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} className={styles.form}>
              {/* Side toggle */}
              <div className={styles.sideToggle}>
                <button
                  type="button"
                  className={`${styles.sideBtn} ${side === "BUY" ? styles.buyActive : ""}`}
                  onClick={() => { setSide("BUY"); setError(null); setResult(null); }}
                >
                  Buy
                </button>
                <button
                  type="button"
                  className={`${styles.sideBtn} ${side === "SELL" ? styles.sellActive : ""}`}
                  onClick={() => { setSide("SELL"); setError(null); setResult(null); }}
                >
                  Sell
                </button>
              </div>

              <div className={styles.field}>
                <label className={styles.fieldLabel}>Quantity</label>
                <input
                  ref={quantityRef}
                  className={styles.input}
                  type="number"
                  placeholder="0"
                  min="0.000001"
                  step="any"
                  value={quantity}
                  onChange={(e) => { setQuantity(e.target.value); setResult(null); }}
                  required
                />
              </div>

              {/* Order summary */}
              <div className={styles.summary}>
                <div className={styles.summaryRow}>
                  <span>Execution price</span>
                  <span>{execPrice ? `$${fmt(execPrice)}` : "Market"}</span>
                </div>
                <div className={styles.summaryRow}>
                  <span>Estimated value</span>
                  <span className={estimatedValue ? styles.summaryHighlight : ""}>
                    {estimatedValue ? `$${fmt(estimatedValue)}` : "—"}
                  </span>
                </div>
                {side === "BUY" && cashBalance && (
                  <div className={styles.summaryRow}>
                    <span>Cash available</span>
                    <span className={willExceedCash ? styles.summaryWarn : ""}>
                      ${fmt(cashBalance)}
                    </span>
                  </div>
                )}
                {side === "SELL" && holding && (
                  <div className={styles.summaryRow}>
                    <span>Shares available</span>
                    <span>{fmt(holding.quantity, 4)}</span>
                  </div>
                )}
              </div>

              {error && <p className={styles.error}>{error}</p>}

              <button
                type="submit"
                className={`${styles.submitBtn} ${side === "SELL" ? styles.submitSell : ""}`}
                disabled={executing || !ticker}
              >
                {executing ? "Placing order…" : `Place ${side} Order`}
              </button>
            </form>
          </div>

          <p className={styles.disclaimer}>
            This is a paper trading simulator. No real money or brokerage accounts are involved.
            Prices are sourced from Yahoo Finance where available, with deterministic synthetic
            pricing as fallback — trades always execute.
          </p>
        </div>
      </div>
    </div>
  );
}
