/**
 * PortfolioContext — global portfolio state store.
 *
 * Provides portfolio summary and live market prices to every page.
 * Polls both endpoints every 3 seconds while authenticated.
 * Silent background refreshes never trigger the loading spinner.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import client from "../api/client";
import { useAuth } from "./AuthContext";

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
  /** Live simulated prices keyed by ticker symbol. Updates every 3 s. */
  marketPrices: Record<string, number>;
  loading: boolean;
  lastUpdated: Date | null;
  /**
   * Fetch the portfolio summary.
   * Pass `silent = true` to suppress the loading spinner (used by the poller).
   */
  refresh: (silent?: boolean) => Promise<void>;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const POLL_MS = 3_000;

// ── Context ────────────────────────────────────────────────────────────────────

const PortfolioContext = createContext<PortfolioContextValue | null>(null);

// ── Provider ───────────────────────────────────────────────────────────────────

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();

  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [marketPrices, setMarketPrices] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Guard against setting state after the component has unmounted.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // ── Portfolio summary ───────────────────────────────────────────────────────

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await client.get<PortfolioSummary>("/portfolio/summary/");
      if (mountedRef.current) {
        setSummary(res.data);
        setLastUpdated(new Date());
      }
    } catch {
      // Keep existing data on error — don't wipe the UI.
    } finally {
      if (!silent && mountedRef.current) setLoading(false);
    }
  }, []);

  // ── Market prices ───────────────────────────────────────────────────────────

  const fetchMarketPrices = useCallback(async () => {
    try {
      const res = await client.get<Record<string, number>>("/market/prices/");
      if (mountedRef.current) setMarketPrices(res.data);
    } catch {
      // Silently ignore — simulator may not have started yet.
    }
  }, []);

  // ── Initial load on authentication ─────────────────────────────────────────

  useEffect(() => {
    if (isAuthenticated) {
      void refresh();
      void fetchMarketPrices();
    } else {
      setSummary(null);
      setMarketPrices({});
    }
  }, [isAuthenticated, refresh, fetchMarketPrices]);

  // ── Live polling ────────────────────────────────────────────────────────────
  // Runs only while authenticated; cleans up automatically on logout or unmount.

  useEffect(() => {
    if (!isAuthenticated) return;

    const id = setInterval(() => {
      void refresh(true);       // silent — no loading spinner
      void fetchMarketPrices();
    }, POLL_MS);

    return () => clearInterval(id);
  }, [isAuthenticated, refresh, fetchMarketPrices]);

  return (
    <PortfolioContext.Provider
      value={{ summary, marketPrices, loading, lastUpdated, refresh }}
    >
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
