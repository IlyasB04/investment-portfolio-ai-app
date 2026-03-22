"""
Portfolio analytics service.

build_portfolio_context(user) → PortfolioContext

Computes a rich, structured snapshot of the user's portfolio state and
returns it as both a typed dataclass and a plain-English narrative string
suitable for injection into an LLM system prompt.

Metrics produced
----------------
  total_equity_value      Sum of all position market values (USD)
  total_with_cash         Equity + cash balance (USD)
  cash_balance            Raw cash balance (USD)
  cash_ratio              cash / total_with_cash  [0–1]
  positions               Per-position breakdown (list of PositionDetail)
  allocation              {ticker: weight}  [0–1] — equity only
  sector_exposure         {sector: aggregate_weight} derived from SECTOR_MAP
  hhi                     Herfindahl–Hirschman Index [0–1], equity only
  concentration_label     "well-diversified" / "moderate" / "concentrated"
  unrealised_pnl_total    Aggregate P&L across all positions (USD)
  unrealised_pnl_pct      Overall return relative to total cost basis
  volatility_proxies      {ticker: annual_vol_estimate}  — from simulator
                          params when available, else CoV from PriceSnapshot
  narrative               Human-readable paragraph summarising the above
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# ── Sector mapping ─────────────────────────────────────────────────────────────
# Static map of common US tickers to GICS-like sector names.
# Unlisted tickers fall back to "Unknown".

SECTOR_MAP: dict[str, str] = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMD":  "Technology", "INTC": "Technology", "GOOGL": "Technology",
    "META": "Technology", "ADBE": "Technology", "CRM": "Technology",
    "ORCL": "Technology", "CSCO": "Technology", "AVGO": "Technology",
    "QCOM": "Technology", "TXN": "Technology",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "NKE":  "Consumer Discretionary", "HD": "Consumer Discretionary",
    "MCD":  "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    # Consumer Staples
    "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "PG": "Consumer Staples", "WMT": "Consumer Staples",
    "COST": "Consumer Staples", "PM": "Consumer Staples",
    # Healthcare
    "JNJ": "Healthcare", "PFE": "Healthcare", "UNH": "Healthcare",
    "ABBV": "Healthcare", "MRK": "Healthcare", "LLY": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare",
    # Financials
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS":  "Financials", "MS": "Financials", "BRK.B": "Financials",
    "V":   "Financials", "MA": "Financials", "AXP": "Financials",
    "BLK": "Financials",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "SLB": "Energy", "OXY": "Energy",
    # Industrials
    "BA": "Industrials", "CAT": "Industrials", "GE": "Industrials",
    "UPS": "Industrials", "RTX": "Industrials", "HON": "Industrials",
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    # Real Estate
    "AMT": "Real Estate", "PLD": "Real Estate", "EQIX": "Real Estate",
    # Communication Services
    "NFLX": "Communication Services", "DIS": "Communication Services",
    "T":   "Communication Services", "VZ": "Communication Services",
    "TMUS": "Communication Services",
    # ETFs — Broad Market
    "SPY": "Index ETF (US Broad)", "VOO": "Index ETF (US Broad)",
    "VTI": "Index ETF (US Broad)", "IVV": "Index ETF (US Broad)",
    "DIA": "Index ETF (US Broad)",
    # ETFs — Sector / Thematic
    "QQQ":  "Index ETF (Tech/Growth)", "IWM": "Index ETF (Small Cap)",
    "ARKK": "Index ETF (Disruptive Innovation)",
    # Commodities ETFs
    "GLD": "Commodities ETF (Gold)", "SLV": "Commodities ETF (Silver)",
    # Fixed Income ETFs
    "TLT": "Fixed Income ETF", "AGG": "Fixed Income ETF",
    "BND": "Fixed Income ETF",
}

# ── Volatility tier fallback ───────────────────────────────────────────────────
# Used when we have no PriceSnapshot history and the simulator isn't running.

_VOL_TIER: dict[str, float] = {
    "TSLA": 0.65, "NVDA": 0.60, "ARKK": 0.55, "AMD": 0.50,
    "META": 0.35, "INTC": 0.35, "AMZN": 0.30,
    "AAPL": 0.25, "MSFT": 0.25, "GOOGL": 0.28,
    "QQQ":  0.20, "IWM":  0.20,
    "SPY":  0.16, "VTI":  0.16, "VOO":  0.16, "DIA": 0.15,
    "GLD":  0.15, "TLT":  0.12, "KO":   0.12,
}
_DEFAULT_VOL = 0.30  # fallback for unlisted tickers


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PositionDetail:
    ticker: str
    quantity: float
    average_cost: float
    current_price: float
    market_value: float
    unrealised_pnl: float
    unrealised_pnl_pct: float
    sector: str
    annual_vol_estimate: float
    price_source: str           # "simulated" | "synthetic"


@dataclass
class PortfolioContext:
    # ── Core financials ────────────────────────────────────────────────────────
    total_equity_value: float
    total_with_cash: float
    cash_balance: float
    cash_ratio: float           # cash / total_with_cash

    # ── Positions ─────────────────────────────────────────────────────────────
    positions: list[PositionDetail] = field(default_factory=list)

    # ── Weights ───────────────────────────────────────────────────────────────
    allocation: dict[str, float] = field(default_factory=dict)     # {ticker: weight [0-1]}
    sector_exposure: dict[str, float] = field(default_factory=dict) # {sector: weight [0-1]}

    # ── Risk metrics ──────────────────────────────────────────────────────────
    hhi: float = 0.0            # Herfindahl-Hirschman Index [0-1]
    concentration_label: str = "n/a"

    # ── P&L ───────────────────────────────────────────────────────────────────
    unrealised_pnl_total: float = 0.0
    unrealised_pnl_pct: float = 0.0  # relative to total cost basis

    # ── Drawdown / movers ─────────────────────────────────────────────────────
    drawdown_estimate: float = 0.0         # max single-position loss% as portfolio proxy
    largest_gainers: list[PositionDetail] = field(default_factory=list)   # top 3 by PnL%
    largest_losers:  list[PositionDetail] = field(default_factory=list)   # bottom 3 by PnL%

    # ── Volatility ────────────────────────────────────────────────────────────
    volatility_proxies: dict[str, float] = field(default_factory=dict)  # {ticker: σ_annual}
    weighted_portfolio_vol: float = 0.0  # simple weighted average of position vols

    # ── Narrative ─────────────────────────────────────────────────────────────
    narrative: str = ""

    # ── Serialisation helpers ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """
        Return a JSON-serialisable dict of the full portfolio context.
        Stored in IntelligenceAuditLog.analytics_snapshot.
        """
        def _pos(p: PositionDetail) -> dict:
            return {
                "ticker":             p.ticker,
                "quantity":           round(p.quantity, 4),
                "average_cost":       round(p.average_cost, 4),
                "current_price":      round(p.current_price, 4),
                "market_value":       round(p.market_value, 2),
                "unrealised_pnl":     round(p.unrealised_pnl, 2),
                "unrealised_pnl_pct": round(p.unrealised_pnl_pct, 2),
                "sector":             p.sector,
                "annual_vol":         round(p.annual_vol_estimate, 4),
                "price_source":       p.price_source,
            }

        return {
            "total_equity_value":    self.total_equity_value,
            "total_with_cash":       self.total_with_cash,
            "cash_balance":          self.cash_balance,
            "cash_ratio":            round(self.cash_ratio, 4),
            "positions":             [_pos(p) for p in self.positions],
            "allocation":            self.allocation,
            "sector_exposure":       self.sector_exposure,
            "hhi":                   round(self.hhi, 4),
            "concentration_label":   self.concentration_label,
            "unrealised_pnl_total":  self.unrealised_pnl_total,
            "unrealised_pnl_pct":    round(self.unrealised_pnl_pct, 2),
            "drawdown_estimate":     round(self.drawdown_estimate, 4),
            "largest_gainers":       [_pos(p) for p in self.largest_gainers],
            "largest_losers":        [_pos(p) for p in self.largest_losers],
            "volatility_proxies":    self.volatility_proxies,
            "weighted_portfolio_vol": round(self.weighted_portfolio_vol, 4),
        }

    def to_intel_prompt(self) -> str:
        """
        Compact text block for injection into a local LLM prompt.

        Targets ~800 tokens — fits within Mistral 7B's 4096 context window
        alongside retrieved chunks (~600 tokens) and the user question.
        """
        lines: list[str] = []
        lines.append("=== PORTFOLIO SNAPSHOT ===")
        lines.append(
            f"Total: ${self.total_with_cash:,.0f}  "
            f"(Equity ${self.total_equity_value:,.0f}  Cash ${self.cash_balance:,.0f} / "
            f"{self.cash_ratio*100:.0f}%)"
        )
        lines.append(
            f"P&L: {'+' if self.unrealised_pnl_total >= 0 else ''}${self.unrealised_pnl_total:,.0f}"
            f" ({'+' if self.unrealised_pnl_pct >= 0 else ''}{self.unrealised_pnl_pct:.1f}%)"
            f"  HHI: {self.hhi:.3f} ({self.concentration_label})"
            f"  PortVol: ~{self.weighted_portfolio_vol*100:.0f}%/yr"
        )

        if self.positions:
            lines.append("POSITIONS:")
            for p in sorted(self.positions, key=lambda x: x.market_value, reverse=True):
                sign = "+" if p.unrealised_pnl >= 0 else ""
                lines.append(
                    f"  {p.ticker} {p.quantity:.2f}sh @ ${p.current_price:.2f}"
                    f" | val ${p.market_value:,.0f}"
                    f" | pnl {sign}${p.unrealised_pnl:,.0f} ({sign}{p.unrealised_pnl_pct:.1f}%)"
                    f" | {p.sector}"
                )

        if self.sector_exposure:
            lines.append("SECTORS: " + "  ".join(
                f"{s}:{w*100:.0f}%"
                for s, w in list(self.sector_exposure.items())[:5]
            ))

        if self.largest_gainers:
            lines.append("TOP GAINERS: " + "  ".join(
                f"{p.ticker} +{p.unrealised_pnl_pct:.1f}%"
                for p in self.largest_gainers
            ))
        if self.largest_losers:
            lines.append("TOP LOSERS: " + "  ".join(
                f"{p.ticker} {p.unrealised_pnl_pct:.1f}%"
                for p in self.largest_losers
            ))

        return "\n".join(lines)


# ── Price resolution ──────────────────────────────────────────────────────────

def _get_price(ticker: str, average_cost: Decimal) -> tuple[float, str]:
    """
    Return (price, source).  Tries simulator first, falls back to synthetic.
    Never raises.
    """
    try:
        from ..simulator import ensure_tracked
        p = ensure_tracked(ticker)
        if p and p > 0:
            return float(p), "simulated"
    except Exception as exc:
        logger.debug("Simulator unavailable for %s: %s", ticker, exc)

    # Deterministic synthetic fallback
    import hashlib
    digest = hashlib.sha256(ticker.upper().encode()).hexdigest()
    seed = int(digest[:8], 16)
    ratio = Decimal(seed) / Decimal(0xFFFF_FFFF)
    mult = Decimal("0.85") + ratio * Decimal("0.50")
    return float((average_cost * mult).quantize(Decimal("0.0001"))), "synthetic"


# ── Volatility estimation ─────────────────────────────────────────────────────

def _estimate_vol(ticker: str) -> float:
    """
    Best-effort annual volatility estimate.

    Priority:
      1. Simulator SYMBOL_PARAMS (exact parameterisation used for simulation)
      2. Coefficient of Variation from PriceSnapshot history (if ≥ 3 records)
      3. Static _VOL_TIER lookup
      4. _DEFAULT_VOL (0.30)
    """
    # 1. Simulator params
    try:
        from ..simulator import SYMBOL_PARAMS, _DEFAULT_PARAMS
        _mu, sigma = SYMBOL_PARAMS.get(ticker.upper(), _DEFAULT_PARAMS)
        return sigma
    except Exception:
        pass

    # 2. Price history CoV
    try:
        from ..models import PriceSnapshot
        snaps = list(
            PriceSnapshot.objects.filter(ticker=ticker)
            .order_by("-as_of")
            .values_list("price", flat=True)[:30]
        )
        if len(snaps) >= 3:
            prices = [float(p) for p in snaps]
            mean_p = statistics.mean(prices)
            if mean_p > 0:
                cov = statistics.stdev(prices) / mean_p
                # Scale CoV (across snapshot interval) to approximate annual vol.
                # Conservative: multiply by sqrt(252) assuming daily snapshots.
                return min(cov * (252 ** 0.5), 2.0)
    except Exception:
        pass

    # 3. Static tier / default
    return _VOL_TIER.get(ticker.upper(), _DEFAULT_VOL)


# ── HHI computation ───────────────────────────────────────────────────────────

def _hhi(weights: list[float]) -> float:
    """Herfindahl-Hirschman Index: sum of squared weights. Range [0, 1]."""
    if not weights:
        return 0.0
    return sum(w ** 2 for w in weights)


def _concentration_label(hhi: float) -> str:
    if hhi >= 0.25:
        return "concentrated"
    if hhi >= 0.15:
        return "moderate"
    return "well-diversified"


# ── Main entry point ──────────────────────────────────────────────────────────

def build_portfolio_context(user) -> PortfolioContext:
    """
    Compute a full PortfolioContext for `user` and return it.

    This is the single entry point called by the RAG orchestrator.
    All data is fetched inside this function — no arguments beyond the user
    object are needed.
    """
    from ..models import Holding, PortfolioAccount, Transaction

    holdings = list(Holding.objects.filter(user=user).order_by("ticker"))
    account, _ = PortfolioAccount.objects.get_or_create(user=user)
    cash = float(account.cash_balance)

    logger.info("[analytics] Building context for user=%s holdings=%d", user.id, len(holdings))

    positions: list[PositionDetail] = []
    total_equity = 0.0
    total_cost_basis = 0.0

    for h in holdings:
        price, source = _get_price(h.ticker, h.average_cost)
        qty = float(h.quantity)
        avg_cost = float(h.average_cost)
        mkt_val = price * qty
        pnl = (price - avg_cost) * qty
        pnl_pct = ((price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0.0
        vol = _estimate_vol(h.ticker)

        positions.append(PositionDetail(
            ticker=h.ticker,
            quantity=qty,
            average_cost=avg_cost,
            current_price=price,
            market_value=mkt_val,
            unrealised_pnl=pnl,
            unrealised_pnl_pct=pnl_pct,
            sector=SECTOR_MAP.get(h.ticker.upper(), "Unknown"),
            annual_vol_estimate=vol,
            price_source=source,
        ))

        total_equity += mkt_val
        total_cost_basis += avg_cost * qty

    total_with_cash = total_equity + cash
    cash_ratio = (cash / total_with_cash) if total_with_cash > 0 else 1.0

    # ── Allocation weights ────────────────────────────────────────────────────
    allocation: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}

    if total_equity > 0:
        for p in positions:
            w = p.market_value / total_equity
            allocation[p.ticker] = round(w, 6)

            sector_exposure[p.sector] = sector_exposure.get(p.sector, 0.0) + w

    # ── Concentration (HHI on equity weights) ─────────────────────────────────
    weights = list(allocation.values())
    hhi = _hhi(weights)
    conc_label = _concentration_label(hhi)

    # ── P&L summary ───────────────────────────────────────────────────────────
    pnl_total = sum(p.unrealised_pnl for p in positions)
    pnl_pct_total = ((pnl_total / total_cost_basis) * 100) if total_cost_basis > 0 else 0.0

    # ── Drawdown estimate + movers ────────────────────────────────────────────
    # Use the worst single-position PnL% as a conservative drawdown proxy.
    if positions:
        drawdown_estimate = min(
            (p.unrealised_pnl_pct / 100 for p in positions), default=0.0
        )
        sorted_by_pnl = sorted(positions, key=lambda p: p.unrealised_pnl_pct, reverse=True)
        largest_gainers = [p for p in sorted_by_pnl[:3] if p.unrealised_pnl_pct > 0]
        largest_losers  = [p for p in sorted_by_pnl[-3:][::-1] if p.unrealised_pnl_pct < 0]
    else:
        drawdown_estimate = 0.0
        largest_gainers   = []
        largest_losers    = []

    # ── Volatility proxies + weighted portfolio vol ───────────────────────────
    vol_proxies: dict[str, float] = {p.ticker: p.annual_vol_estimate for p in positions}
    if total_equity > 0:
        w_vol = sum(allocation.get(p.ticker, 0) * p.annual_vol_estimate for p in positions)
    else:
        w_vol = 0.0

    # ── Narrative ─────────────────────────────────────────────────────────────
    narrative = _build_narrative(
        positions=positions,
        total_equity=total_equity,
        total_with_cash=total_with_cash,
        cash=cash,
        cash_ratio=cash_ratio,
        allocation=allocation,
        sector_exposure=sector_exposure,
        hhi=hhi,
        conc_label=conc_label,
        pnl_total=pnl_total,
        pnl_pct_total=pnl_pct_total,
        w_vol=w_vol,
        user=user,
    )

    ctx = PortfolioContext(
        total_equity_value=round(total_equity, 2),
        total_with_cash=round(total_with_cash, 2),
        cash_balance=round(cash, 2),
        cash_ratio=round(cash_ratio, 4),
        positions=positions,
        allocation={k: round(v, 4) for k, v in allocation.items()},
        sector_exposure={k: round(v, 4) for k, v in sorted(
            sector_exposure.items(), key=lambda x: x[1], reverse=True
        )},
        hhi=round(hhi, 4),
        concentration_label=conc_label,
        unrealised_pnl_total=round(pnl_total, 2),
        unrealised_pnl_pct=round(pnl_pct_total, 2),
        drawdown_estimate=round(drawdown_estimate, 4),
        largest_gainers=largest_gainers,
        largest_losers=largest_losers,
        volatility_proxies={k: round(v, 4) for k, v in vol_proxies.items()},
        weighted_portfolio_vol=round(w_vol, 4),
        narrative=narrative,
    )

    logger.info(
        "[analytics] Context built: equity=$%.2f cash=$%.2f positions=%d HHI=%.3f PnL=$%.2f",
        total_equity, cash, len(positions), hhi, pnl_total,
    )
    return ctx


# ── Narrative builder ─────────────────────────────────────────────────────────

def _build_narrative(
    *,
    positions: list[PositionDetail],
    total_equity: float,
    total_with_cash: float,
    cash: float,
    cash_ratio: float,
    allocation: dict[str, float],
    sector_exposure: dict[str, float],
    hhi: float,
    conc_label: str,
    pnl_total: float,
    pnl_pct_total: float,
    w_vol: float,
    user,
) -> str:
    """Produce a structured, readable text block for LLM injection."""
    lines: list[str] = []

    # ── Header ──
    lines.append("=== PORTFOLIO SNAPSHOT ===")
    lines.append(f"Total portfolio value (equities + cash): ${total_with_cash:,.2f}")
    lines.append(f"  Equity holdings: ${total_equity:,.2f}")
    lines.append(f"  Cash balance:    ${cash:,.2f}  ({cash_ratio*100:.1f}% of portfolio)")
    lines.append("")

    # ── Positions ──
    if not positions:
        lines.append("HOLDINGS: None — the portfolio is empty.")
    else:
        lines.append(f"HOLDINGS ({len(positions)} positions):")
        for p in sorted(positions, key=lambda x: x.market_value, reverse=True):
            sign = "+" if p.unrealised_pnl >= 0 else ""
            price_tag = "" if p.price_source == "simulated" else " [synthetic price]"
            lines.append(
                f"  {p.ticker:<6} {p.quantity:.4f} shares @ ${p.current_price:.2f}{price_tag}"
                f"  |  mkt value ${p.market_value:,.2f}"
                f"  |  P&L {sign}${p.unrealised_pnl:,.2f} ({sign}{p.unrealised_pnl_pct:.2f}%)"
                f"  |  sector: {p.sector}"
            )

        lines.append("")
        lines.append(
            f"TOTAL UNREALISED P&L: {'+'if pnl_total>=0 else ''}${pnl_total:,.2f}"
            f"  ({'+' if pnl_pct_total>=0 else ''}{pnl_pct_total:.2f}% on cost basis)"
        )

    # ── Allocation ──
    if allocation:
        lines.append("")
        lines.append("ALLOCATION (% of equity):")
        for ticker, w in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(w * 20)
            lines.append(f"  {ticker:<6} {w*100:5.1f}%  {bar}")

    # ── Sector exposure ──
    if sector_exposure:
        lines.append("")
        lines.append("SECTOR EXPOSURE (% of equity):")
        for sector, w in sector_exposure.items():
            lines.append(f"  {sector:<35} {w*100:5.1f}%")

    # ── Concentration risk ──
    lines.append("")
    lines.append(f"CONCENTRATION RISK:")
    lines.append(f"  HHI: {hhi:.4f}  →  {conc_label.upper()}")
    lines.append(
        "  (HHI < 0.15 = well-diversified | 0.15–0.25 = moderate | > 0.25 = concentrated)"
    )
    if positions:
        top_ticker = max(positions, key=lambda p: p.market_value).ticker
        top_w = allocation.get(top_ticker, 0)
        lines.append(f"  Largest position: {top_ticker} at {top_w*100:.1f}% of equity")

    # ── Volatility ──
    lines.append("")
    lines.append(f"VOLATILITY PROFILE:")
    lines.append(f"  Weighted portfolio vol (annual): ~{w_vol*100:.1f}%")
    if positions:
        for p in sorted(positions, key=lambda x: x.annual_vol_estimate, reverse=True):
            tier = (
                "HIGH" if p.annual_vol_estimate >= 0.45 else
                "MED"  if p.annual_vol_estimate >= 0.20 else "LOW"
            )
            lines.append(f"  {p.ticker:<6} σ≈{p.annual_vol_estimate*100:.0f}%/yr  [{tier}]")

    # ── Recent transactions ──
    try:
        from ..models import Transaction
        txns = list(
            Transaction.objects.filter(user=user)
            .order_by("-created_at")[:8]
        )
        if txns:
            lines.append("")
            lines.append("RECENT TRANSACTIONS (newest first):")
            for t in txns:
                lines.append(
                    f"  {t.created_at.strftime('%Y-%m-%d')} {t.side} "
                    f"{float(t.quantity):.4f} {t.ticker} @ ${float(t.price):.2f}"
                    f"  total ${float(t.total_value):,.2f}"
                )
    except Exception:
        pass

    return "\n".join(lines)
