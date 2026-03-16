import { useEffect, useRef, useState } from "react";
import client from "../api/client";
import styles from "./InstrumentSearch.module.css";

interface Instrument {
  ticker: string;
  name: string;
  type: string;
  exchange: string;
}

interface Props {
  onTrade: (ticker: string, side: "BUY" | "SELL") => void;
}

export default function InstrumentSearch({ onTrade }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Instrument[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Debounced search
  useEffect(() => {
    if (query.trim().length < 1) { setResults([]); setOpen(false); return; }
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await client.get<Instrument[]>("/market/search/", { params: { q: query } });
        setResults(res.data);
        setOpen(res.data.length > 0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <div className={styles.inputWrap}>
        <span className={styles.icon}>⌕</span>
        <input
          className={styles.input}
          type="text"
          placeholder="Search stocks & ETFs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
        />
        {loading && <span className={styles.spinner}>…</span>}
      </div>

      {open && (
        <div className={styles.dropdown}>
          {results.map((r) => (
            <div key={r.ticker} className={styles.result}>
              <div className={styles.resultMeta}>
                <span className={styles.resultTicker}>{r.ticker}</span>
                <span className={styles.resultName}>{r.name}</span>
                <span className={styles.resultBadge}>{r.type}</span>
              </div>
              <div className={styles.resultActions}>
                <button
                  className={`${styles.actionBtn} ${styles.buy}`}
                  onClick={() => { setOpen(false); setQuery(""); onTrade(r.ticker, "BUY"); }}
                >Buy</button>
                <button
                  className={`${styles.actionBtn} ${styles.sell}`}
                  onClick={() => { setOpen(false); setQuery(""); onTrade(r.ticker, "SELL"); }}
                >Sell</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
