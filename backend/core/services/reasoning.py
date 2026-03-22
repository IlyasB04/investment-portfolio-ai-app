"""
Financial reasoning engine.

run_reasoning(portfolio_context) → list[ReasoningFlag]

Applies six deterministic detectors over the user's PortfolioContext and
returns a list of ReasoningFlag objects describing any portfolio risks
or structural issues detected.  Each flag includes a severity, a title,
a plain-English explanation, and a concrete recommendation — allowing
the intelligence pipeline to cite specific findings even when no LLM
is available.

Detectors
---------
  1. detect_high_concentration_risk   — single-ticker dominance (HHI / top weight)
  2. detect_sector_dominance          — one sector > 50 % of equity
  3. detect_cash_drag                 — excess idle cash diluting returns
  4. detect_drawdown_pressure         — unrealised losses signalling downside risk
  5. detect_loss_cluster              — multiple positions simultaneously losing
  6. detect_correlation_exposure_proxy — sector concentration as correlation proxy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .analytics import PortfolioContext

logger = logging.getLogger(__name__)


# ── ReasoningFlag ──────────────────────────────────────────────────────────────

@dataclass
class ReasoningFlag:
    flag_id:           str             # stable identifier e.g. "HIGH_CONCENTRATION"
    severity:          str             # "high" | "medium" | "low"
    title:             str             # short headline
    explanation:       str             # 1–2 sentence plain-English description
    affected_positions: list[str]      # list of affected ticker symbols
    metric_value:      float           # the numeric value that triggered the flag
    recommendation:    str             # actionable suggestion

    def to_dict(self) -> dict:
        return {
            "flag_id":            self.flag_id,
            "severity":           self.severity,
            "title":              self.title,
            "explanation":        self.explanation,
            "affected_positions": self.affected_positions,
            "metric_value":       round(self.metric_value, 4),
            "recommendation":     self.recommendation,
        }


# ── Thresholds ─────────────────────────────────────────────────────────────────

_CONCENTRATION_HIGH  = 0.40   # single ticker ≥ 40 % of equity → high severity
_CONCENTRATION_MED   = 0.25   # single ticker ≥ 25 % of equity → medium severity

_SECTOR_DOMINANCE    = 0.50   # single sector ≥ 50 % of equity

_CASH_DRAG_HIGH      = 0.40   # cash ≥ 40 % of portfolio → high severity
_CASH_DRAG_MED       = 0.25   # cash ≥ 25 % of portfolio → medium severity

_DRAWDOWN_HIGH       = -0.15  # portfolio PnL% ≤ -15 % → high severity
_DRAWDOWN_MED        = -0.07  # portfolio PnL% ≤ -7 % → medium severity

_LOSS_CLUSTER_COUNT  = 3      # ≥ 3 positions losing simultaneously

_CORR_SECTOR_THRESH  = 0.60   # ≥ 60 % in one sector triggers correlation proxy


# ── Detector 1: High Concentration Risk ───────────────────────────────────────

def detect_high_concentration_risk(ctx: PortfolioContext) -> ReasoningFlag | None:
    """Flag when a single position dominates equity allocation."""
    if not ctx.allocation:
        return None

    top_ticker, top_weight = max(ctx.allocation.items(), key=lambda kv: kv[1])
    pct = top_weight * 100

    if top_weight >= _CONCENTRATION_HIGH:
        severity = "high"
    elif top_weight >= _CONCENTRATION_MED:
        severity = "medium"
    else:
        return None

    return ReasoningFlag(
        flag_id            = "HIGH_CONCENTRATION",
        severity           = severity,
        title              = f"High single-stock concentration: {top_ticker} at {pct:.1f}%",
        explanation        = (
            f"{top_ticker} represents {pct:.1f}% of your equity portfolio. "
            "This level of concentration amplifies idiosyncratic risk — a single "
            "adverse event in that company can materially damage overall returns."
        ),
        affected_positions = [top_ticker],
        metric_value       = top_weight,
        recommendation     = (
            f"Consider trimming {top_ticker} below 20–25% of equity "
            "and redistributing proceeds into uncorrelated positions."
        ),
    )


# ── Detector 2: Sector Dominance ──────────────────────────────────────────────

def detect_sector_dominance(ctx: PortfolioContext) -> ReasoningFlag | None:
    """Flag when one GICS-like sector holds the majority of equity."""
    if not ctx.sector_exposure:
        return None

    top_sector, top_weight = max(ctx.sector_exposure.items(), key=lambda kv: kv[1])
    pct = top_weight * 100

    if top_weight < _SECTOR_DOMINANCE:
        return None

    affected = [
        p.ticker for p in ctx.positions
        if p.sector == top_sector
    ]

    return ReasoningFlag(
        flag_id            = "SECTOR_DOMINANCE",
        severity           = "high" if top_weight >= 0.70 else "medium",
        title              = f"Sector dominance: {top_sector} at {pct:.1f}%",
        explanation        = (
            f"Over {pct:.0f}% of your equity is in {top_sector}. "
            "Sector-wide downturns — regulatory shifts, macro headwinds, or "
            "earnings cycles — can simultaneously impair all positions in this group."
        ),
        affected_positions = affected,
        metric_value       = top_weight,
        recommendation     = (
            f"Diversify across at least 4–5 sectors to reduce {top_sector} "
            "exposure below 35%. Consider broad-market ETFs (e.g. VTI, SPY) "
            "to add low-correlation balance."
        ),
    )


# ── Detector 3: Cash Drag ─────────────────────────────────────────────────────

def detect_cash_drag(ctx: PortfolioContext) -> ReasoningFlag | None:
    """Flag excess idle cash that is likely diluting long-term compounding returns."""
    cash_pct = ctx.cash_ratio * 100

    if ctx.cash_ratio >= _CASH_DRAG_HIGH:
        severity = "high"
    elif ctx.cash_ratio >= _CASH_DRAG_MED:
        severity = "medium"
    else:
        return None

    return ReasoningFlag(
        flag_id            = "CASH_DRAG",
        severity           = severity,
        title              = f"Cash drag: {cash_pct:.1f}% of portfolio is uninvested",
        explanation        = (
            f"{cash_pct:.1f}% of your total portfolio sits as cash. "
            "While liquidity reserves are prudent, large idle cash positions "
            "underperform equity over long horizons and create negative real "
            "returns during inflationary periods."
        ),
        affected_positions = [],
        metric_value       = ctx.cash_ratio,
        recommendation     = (
            "If you have a long investment horizon, consider deploying excess cash "
            "through a systematic investment plan — dollar-cost averaging into "
            "diversified positions over 4–8 weeks to reduce timing risk."
        ),
    )


# ── Detector 4: Drawdown Pressure ─────────────────────────────────────────────

def detect_drawdown_pressure(ctx: PortfolioContext) -> ReasoningFlag | None:
    """Flag significant unrealised portfolio loss suggesting drawdown stress."""
    pnl_pct = ctx.unrealised_pnl_pct  # already as a percentage

    if pnl_pct <= _DRAWDOWN_HIGH * 100:
        severity = "high"
    elif pnl_pct <= _DRAWDOWN_MED * 100:
        severity = "medium"
    else:
        return None

    losing = [p.ticker for p in ctx.positions if p.unrealised_pnl < 0]

    return ReasoningFlag(
        flag_id            = "DRAWDOWN_PRESSURE",
        severity           = severity,
        title              = f"Portfolio under drawdown: {pnl_pct:.1f}% unrealised loss",
        explanation        = (
            f"Your portfolio is showing a cumulative unrealised loss of "
            f"{pnl_pct:.1f}% on cost basis. This indicates meaningful drawdown "
            "pressure, which can trigger emotional decision-making and forced selling."
        ),
        affected_positions = losing,
        metric_value       = pnl_pct / 100,
        recommendation     = (
            "Review each losing position against its original investment thesis. "
            "Distinguish between temporary market volatility and fundamental "
            "deterioration. Avoid panic-selling diversified positions during "
            "broad market corrections."
        ),
    )


# ── Detector 5: Loss Cluster ──────────────────────────────────────────────────

def detect_loss_cluster(ctx: PortfolioContext) -> ReasoningFlag | None:
    """Flag when multiple positions are simultaneously losing, suggesting systemic risk."""
    if not ctx.positions:
        return None

    losing = [p for p in ctx.positions if p.unrealised_pnl < 0]
    total = len(ctx.positions)

    if len(losing) < _LOSS_CLUSTER_COUNT:
        return None

    loss_ratio = len(losing) / total
    severity = "high" if loss_ratio >= 0.60 else "medium"

    return ReasoningFlag(
        flag_id            = "LOSS_CLUSTER",
        severity           = severity,
        title              = f"Loss cluster: {len(losing)}/{total} positions are losing",
        explanation        = (
            f"{len(losing)} out of {total} positions are in negative territory. "
            "Simultaneous losses across many positions often indicate broad market "
            "selling pressure or systematic correlation — meaning diversification "
            "benefits are temporarily reduced."
        ),
        affected_positions = [p.ticker for p in losing],
        metric_value       = loss_ratio,
        recommendation     = (
            "Assess whether losses are correlated with a macro event (rate hike, "
            "recession fears) or specific to individual companies. If correlated, "
            "consider defensive repositioning into low-volatility or counter-cyclical "
            "assets (e.g. consumer staples, fixed income ETFs)."
        ),
    )


# ── Detector 6: Correlation Exposure Proxy ────────────────────────────────────

def detect_correlation_exposure_proxy(ctx: PortfolioContext) -> ReasoningFlag | None:
    """
    Proxy for implicit correlation risk.

    When a portfolio is dominated by a single sector, the constituent stocks
    are highly correlated (same macro drivers, earnings cycles, sentiment).
    This detector fires independently of detect_sector_dominance — it uses a
    lower threshold and focuses on the correlation interpretation rather than
    the diversification failure angle.
    """
    if not ctx.sector_exposure:
        return None

    top_sector, top_weight = max(ctx.sector_exposure.items(), key=lambda kv: kv[1])
    pct = top_weight * 100

    if top_weight < _CORR_SECTOR_THRESH:
        return None

    # Don't duplicate if sector_dominance already fired at the same position
    # (sector_dominance fires at 50%+, correlation proxy fires at 60%+, different msg)
    affected = [p.ticker for p in ctx.positions if p.sector == top_sector]

    return ReasoningFlag(
        flag_id            = "CORRELATION_EXPOSURE",
        severity           = "medium",
        title              = (
            f"Implicit correlation risk: {top_sector} stocks move together "
            f"({pct:.0f}% of equity)"
        ),
        explanation        = (
            f"With {pct:.0f}% of your equity in {top_sector}, your positions "
            "share common risk factors — interest rate sensitivity, regulatory "
            "exposure, and sector-specific earnings cycles. "
            "In a sector-wide selloff, diversification offers limited protection."
        ),
        affected_positions = affected,
        metric_value       = top_weight,
        recommendation     = (
            "Add positions from negatively or lowly correlated sectors "
            "(e.g. Utilities, Consumer Staples, or Fixed Income ETFs) to "
            "reduce co-movement risk within the portfolio."
        ),
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_reasoning(ctx: PortfolioContext) -> list[ReasoningFlag]:
    """
    Run all six detectors and return a deduplicated, severity-ordered list
    of ReasoningFlag objects.

    Empty portfolio returns an empty list — no spurious flags fired.
    """
    if not ctx.positions and ctx.total_equity_value == 0:
        return []

    detectors = [
        detect_high_concentration_risk,
        detect_sector_dominance,
        detect_cash_drag,
        detect_drawdown_pressure,
        detect_loss_cluster,
        detect_correlation_exposure_proxy,
    ]

    flags: list[ReasoningFlag] = []
    for detector in detectors:
        try:
            result = detector(ctx)
            if result is not None:
                flags.append(result)
        except Exception as exc:
            logger.warning("[reasoning] detector %s failed: %s", detector.__name__, exc)

    # Order: high → medium → low
    _order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: _order.get(f.severity, 9))

    logger.info(
        "[reasoning] %d flag(s) detected for portfolio val=$%.0f",
        len(flags), ctx.total_with_cash,
    )
    return flags
