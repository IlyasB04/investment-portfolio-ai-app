import { FormEvent, useEffect, useRef, useState } from "react";
import axios from "axios";
import client from "../api/client";
import styles from "./TradeModal.module.css";

interface TradeModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

interface HoldingPayload {
  ticker: string;
  quantity: number;
  average_cost: number;
}

export default function TradeModal({ onClose, onSuccess }: TradeModalProps) {
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const overlayRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === overlayRef.current) onClose();
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const qty = parseFloat(quantity);
    const avgCost = parseFloat(price);

    if (qty <= 0 || avgCost <= 0) {
      setError("Quantity and price must be positive numbers.");
      return;
    }

    const payload: HoldingPayload = {
      ticker: ticker.trim().toUpperCase(),
      quantity: qty,
      average_cost: avgCost,
    };

    setLoading(true);
    try {
      await client.post("/holdings/", payload);
      onSuccess();
      onClose();
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.data) {
        const data = err.response.data as Record<string, string[]>;
        const first = Object.values(data).flat()[0];
        setError(first ?? "Failed to create holding.");
      } else {
        setError("Failed to create holding. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.overlay} ref={overlayRef} onClick={handleOverlayClick}>
      <div className={styles.card} role="dialog" aria-modal="true" aria-label="Add Trade">
        <div className={styles.cardHeader}>
          <h2 className={styles.title}>Add Trade</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="ticker">Ticker</label>
            <input
              id="ticker"
              className={styles.input}
              type="text"
              placeholder="e.g. AAPL"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="quantity">Quantity</label>
              <input
                id="quantity"
                className={styles.input}
                type="number"
                placeholder="0.00"
                min="0.000001"
                step="any"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                required
              />
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="price">Price per share</label>
              <input
                id="price"
                className={styles.input}
                type="number"
                placeholder="0.00"
                min="0.000001"
                step="any"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                required
              />
            </div>
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <div className={styles.actions}>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </button>
            <button type="submit" className={styles.submitBtn} disabled={loading}>
              {loading ? "Adding…" : "Add Trade"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
