/**
 * PortfolioContext — global portfolio state store.
 *
 * Provides the current portfolio summary to every page without each
 * page independently fetching it.  After a trade or import, call
 * `refresh()` to pull fresh data and update all consumers.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import client from "../api/client";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Position {
  id: number;
  ticker: string;
  quantity: string;
  average_cost: string;
  price: string;
  market_value: string;
  pnl: string;
  is_synthetic_price: boolean;
}

export interface Allocation {
  ticker: string;
  market_value: string;
  percent_of_portfolio: string;
}

export interface PortfolioSummary {
  total_value: string;
  cash_balance: string;
  total_with_cash: string;
  positions: Position[];
  allocation: Allocation[];
  concentration: {
    top1_percent: number;
    top3_percent: number;
  };
}

interface PortfolioContextValue {
  summary: PortfolioSummary | null;
  loading: boolean;
  lastUpdated: Date | null;
  refresh: () => Promise<void>;
}

// ── Context ────────────────────────────────────────────────────────────────────

const PortfolioContext = createContext<PortfolioContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────────

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await client.get<PortfolioSummary>("/portfolio/summary/");
      setSummary(res.data);
      setLastUpdated(new Date());
    } catch {
      // Keep existing data on error — don't wipe the UI
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load — only when the user is authenticated (client has token)
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) refresh();
  }, [refresh]);

  return (
    <PortfolioContext.Provider value={{ summary, loading, lastUpdated, refresh }}>
      {children}
    </PortfolioContext.Provider>
  );
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function usePortfolio(): PortfolioContextValue {
  const ctx = useContext(PortfolioContext);
  if (!ctx) {
    throw new Error("usePortfolio must be used inside <PortfolioProvider>");
  }
  return ctx;
}
