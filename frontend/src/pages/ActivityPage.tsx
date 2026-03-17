import { useCallback, useEffect, useState } from "react";
import client from "../api/client";
import styles from "./ActivityPage.module.css";

interface Transaction {
  id: number;
  ticker: string;
  side: "BUY" | "SELL";
  quantity: string;
  price: string;
  total_value: string;
  created_at: string;
  notes?: string;
}

function fmt(v: string | number, dec = 2) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ActivityPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"ALL" | "BUY" | "SELL">("ALL");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await client.get<Transaction[]>("/orders/transactions/");
      setTransactions(res.data);
    } catch {
      setError("Failed to load transaction history.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = transactions.filter((t) => {
    if (filter !== "ALL" && t.side !== filter) return false;
    if (search && !t.ticker.toUpperCase().includes(search.toUpperCase())) return false;
    return true;
  });

  const totalBuys = transactions.filter((t) => t.side === "BUY").reduce((s, t) => s + parseFloat(t.total_value), 0);
  const totalSells = transactions.filter((t) => t.side === "SELL").reduce((s, t) => s + parseFloat(t.total_value), 0);

  return (
    <div className={styles.page}>
      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Activity</h1>
          <p className={styles.pageSubtitle}>Full transaction history — all paper trades</p>
        </div>
      </div>

      {/* ── Summary cards ── */}
      <div className={styles.summaryRow}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Total Trades</span>
          <span className={styles.statValue}>{transactions.length}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Total Bought</span>
          <span className={`${styles.statValue} ${styles.positive}`}>${fmt(totalBuys)}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Total Sold</span>
          <span className={`${styles.statValue} ${styles.negative}`}>${fmt(totalSells)}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Net Flow</span>
          <span className={`${styles.statValue} ${totalBuys - totalSells >= 0 ? styles.negative : styles.positive}`}>
            ${fmt(Math.abs(totalBuys - totalSells))}
          </span>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className={styles.controls}>
        <div className={styles.filterGroup}>
          {(["ALL", "BUY", "SELL"] as const).map((f) => (
            <button
              key={f}
              className={`${styles.filterBtn} ${filter === f ? styles.filterActive : ""}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <input
          className={styles.searchInput}
          type="text"
          placeholder="Search ticker…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* ── Table ── */}
      <div className={styles.tableWrap}>
        {loading && <p className={styles.loadingMsg}>Loading transactions…</p>}
        {error && <p className={styles.errorMsg}>{error}</p>}

        {!loading && !error && filtered.length === 0 && (
          <div className={styles.emptyState}>
            <p className={styles.emptyTitle}>No transactions found</p>
            <p className={styles.emptySub}>
              {transactions.length === 0
                ? "You haven't made any trades yet. Head to the Trade page to get started."
                : "No transactions match your current filter."}
            </p>
          </div>
        )}

        {!loading && filtered.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Date</th>
                <th className={styles.th}>Ticker</th>
                <th className={styles.th}>Side</th>
                <th className={`${styles.th} ${styles.right}`}>Qty</th>
                <th className={`${styles.th} ${styles.right}`}>Price</th>
                <th className={`${styles.th} ${styles.right}`}>Total Value</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.id} className={styles.row}>
                  <td className={`${styles.td} ${styles.dateCell}`}>{fmtDate(t.created_at)}</td>
                  <td className={styles.td}>
                    <span className={styles.ticker}>{t.ticker}</span>
                  </td>
                  <td className={styles.td}>
                    <span className={`${styles.sideBadge} ${t.side === "BUY" ? styles.buy : styles.sell}`}>
                      {t.side}
                    </span>
                  </td>
                  <td className={`${styles.td} ${styles.right} ${styles.mono}`}>{fmt(t.quantity, 4)}</td>
                  <td className={`${styles.td} ${styles.right} ${styles.mono}`}>${fmt(t.price)}</td>
                  <td className={`${styles.td} ${styles.right} ${styles.mono} ${styles.totalVal}`}>
                    ${fmt(t.total_value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className={styles.disclaimer}>
        Paper trading simulator — no real money involved. All prices and transactions are for demonstration purposes only.
      </p>
    </div>
  );
}
