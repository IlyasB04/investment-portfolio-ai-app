"""
Question intent classifier for the portfolio intelligence pipeline.

classify_question_intent(question, has_portfolio) → str

Supported intents
-----------------
  portfolio_performance    – portfolio value, P&L, returns, holdings summary
  concentration_risk       – HHI, top-weight, sector exposure, single-stock dominance
  diversification_strategy – how to diversify, asset correlation, spreading risk
  macro_impact             – interest rates, Fed, inflation, recession, sector sensitivity
  finance_theory           – MPT, efficient frontier, Sharpe, academic concepts
  behavioural              – investor psychology, FOMO, panic selling, loss aversion
  rebalancing_allocation   – how to redistribute, target weights, cash deployment
  mixed                    – spans two or more intents
  unsupported              – completely off-topic

Routing implications
--------------------
  Intent                    top_k   Dominant input
  ──────────────────────    ─────   ────────────────────────────────────────────────
  portfolio_performance       2     analytics dominant; minimal theory retrieval
  concentration_risk          4     concentration risk sources + analytics
  diversification_strategy    5     theory sources dominant; portfolio as context
  macro_impact                6     macro/theory sources; portfolio as exposure context
  finance_theory              6     knowledge base dominant; portfolio as application
  behavioural                 4     theory on investor psychology + portfolio context
  rebalancing_allocation      4     asset allocation sources + analytics
  mixed                       5     balanced retrieval + analytics
  unsupported                 0     polite redirect; no retrieval needed
"""

from __future__ import annotations

import re

# ── Intent constants ──────────────────────────────────────────────────────────

PORTFOLIO_PERFORMANCE    = "portfolio_performance"
CONCENTRATION_RISK       = "concentration_risk"
DIVERSIFICATION_STRATEGY = "diversification_strategy"
MACRO_IMPACT             = "macro_impact"
FINANCE_THEORY           = "finance_theory"
BEHAVIOURAL              = "behavioural"
REBALANCING_ALLOCATION   = "rebalancing_allocation"
MIXED                    = "mixed"
UNSUPPORTED              = "unsupported"

# top_k chunks to retrieve per intent
INTENT_TOP_K: dict[str, int] = {
    PORTFOLIO_PERFORMANCE:    2,
    CONCENTRATION_RISK:       4,
    DIVERSIFICATION_STRATEGY: 5,
    MACRO_IMPACT:             6,
    FINANCE_THEORY:           6,
    BEHAVIOURAL:              4,
    REBALANCING_ALLOCATION:   4,
    MIXED:                    5,
    UNSUPPORTED:              0,
}

# ── Pattern sets ──────────────────────────────────────────────────────────────

_CONCENTRATION_PAT = [
    r"\bconcentrat\w*\b", r"\bhhi\b",
    r"\btop\s+position\b", r"\boverweight\b",
    r"\bsingle.?stock\b", r"\btoo\s+much\s+(in|on)\b",
    r"\bsector\s+(risk|weight|exposure)\b",
    r"\bsector\b.+\bexpos\w*\b",
]

_DIVERSIFICATION_PAT = [
    r"\bdiversif\w*\b", r"\bcorrelat\w*\b",
    r"\buncorrelat\w*\b", r"\bspread\s+(the\s+)?risk\b",
    r"\bdifferent\s+(asset|sector|class)\b",
    r"\bnot\s+all\s+eggs\b", r"\basset\s+class\w*\b",
    r"\blow\s+corr\w*\b",
]

_THEORY_PAT = [
    r"\bmodern\s+portfolio\b", r"\bmpt\b", r"\bmarkowitz\b",
    r"\befficient\s+frontier\b", r"\bsharpe\s+ratio\b", r"\balpha\b",
    r"\bbeta\b", r"\btheory\b", r"\bprinciple\b",
    r"\bacademic\b", r"\bresearch\s+says?\b", r"\bwhat\s+does\b.+\bsay\b",
    r"\bvolatility\b", r"\brisk.adjusted\b", r"\bcapital\s+asset\b",
    r"\bexpected\s+return\b", r"\brisk.free\b", r"\bportfolio\s+theory\b",
]

_MACRO_PAT = [
    r"\binterest\s+rates?\b", r"\bfed\b", r"\bfederal\s+reserve\b",
    r"\binflation\b", r"\brecession\b", r"\bgdp\b", r"\bmacro\b",
    r"\beconomy\b", r"\bmarket\s+crash\b", r"\byield\s+curve\b",
    r"\bbond\s+market\b", r"\bcurrency\b", r"\bgeopolit\w*\b",
    r"\brate\s+hike\b", r"\brate\s+cut\b", r"\bcredit\s+crisis\b",
    r"\b(rising|falling|higher|lower)\s+rates?\b",
    r"\brates?\s+(rise|fall|increase|decrease|hike)\b",
    r"\bmarket\s+condition\b", r"\beconomic\s+(outlook|environment|cycle)\b",
]

_REBALANCING_PAT = [
    r"\brebalanc\w*\b", r"\ballocat\w*\b", r"\bredistribut\w*\b",
    r"\btoo\s+much\s+cash\b", r"\bcash\s+drag\b",
    r"\bhow\s+should\s+i\b", r"\bshould\s+i\s+(buy|sell|add|reduce|trim)\b",
    r"\btarget\s+weight\b", r"\boptimal\s+(portfolio|allocation)\b",
    r"\bportfolio\s+construction\b", r"\badd\s+to\b", r"\btrim\b",
]

_PERFORMANCE_PAT = [
    r"\bwhy\b.+\b(down|los(ing|s)|negative|drop(ped)?)\b",
    r"\b(down|losing|dropped?|negative)\b",
    r"\bdrawdown\b", r"\bunderperform\w*\b",
    r"\bwhat\s+happened\b", r"\bwhy\s+is\s+my\b",
    r"\bworst\s+(performer|position|holding)\b", r"\blosers?\b",
    r"\bpoor\s+performance\b", r"\bbad\s+(day|week|month)\b",
    r"\bnegative\s+return\b", r"\bperformance\b", r"\breturns?\b",
    r"\bgains?\b", r"\bprofitable\b", r"\bgainers?\b",
]

_PORTFOLIO_PAT = [
    r"\bmy\s+(portfolio|holdings?|positions?|p&l|pnl|cash|account)\b",
    r"\b(largest|biggest)\b",
    r"\bhow\s+much\b",
    r"\bsummar\w+\b", r"\bwhat\s+is\s+my\b", r"\bhow\s+am\s+i\b",
    r"\bshow\s+me\b", r"\btotal\s+(value|portfolio)\b",
    r"\brecent\s+(transactions?|trades?|activity)\b",
]

_BEHAVIOURAL_PAT = [
    r"\bfomo\b", r"\bloss\s+aversion\b", r"\bsell\s+(everything|all)\b",
    r"\bpanick?\w*\b", r"\bfear\b.*(market|invest|sell)\b",
    r"\bhold\s+(on|tight)\b", r"\bnerv\w+\b",
    r"\bemotional\s+(trading|decision|invest)\b",
    r"\bpsycholog\w*\b", r"\bbehaviour\w*\b", r"\bbehavior\w*\b",
    r"\boverreact\w*\b", r"\birrational\b",
    r"\bshould\s+i\s+(sell|panic|worry)\b",
    r"\bscare[dw]?\b", r"\bshort.term\s+(fear|noise|thinking)\b",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


# ── Main classifier ───────────────────────────────────────────────────────────

def classify_question_intent(
    question: str,
    has_portfolio: bool = True,
) -> str:
    """
    Return the most likely intent string for the given question.

    Uses fast regex pattern matching — zero external dependencies, < 1 ms.
    Resolves ambiguity using a priority ladder; labels mixed when 3+ intents fire.
    """
    q = question.lower().strip()

    hits = {
        CONCENTRATION_RISK:       _match(q, _CONCENTRATION_PAT),
        DIVERSIFICATION_STRATEGY: _match(q, _DIVERSIFICATION_PAT),
        FINANCE_THEORY:           _match(q, _THEORY_PAT),
        MACRO_IMPACT:             _match(q, _MACRO_PAT),
        REBALANCING_ALLOCATION:   _match(q, _REBALANCING_PAT),
        PORTFOLIO_PERFORMANCE:    _match(q, _PERFORMANCE_PAT) or _match(q, _PORTFOLIO_PAT),
        BEHAVIOURAL:              _match(q, _BEHAVIOURAL_PAT),
    }

    matched = [k for k, v in hits.items() if v]

    if not matched:
        # No keywords matched — if user has a portfolio, assume portfolio question;
        # otherwise treat as unsupported.
        if not has_portfolio:
            return UNSUPPORTED
        word_count = len(q.split())
        return PORTFOLIO_PERFORMANCE if word_count <= 20 else MIXED

    if len(matched) == 1:
        return matched[0]

    # 3+ matches → clearly mixed
    if len(matched) >= 3:
        return MIXED

    # 2 matches: resolve by priority (most specific / actionable wins)
    priority = [
        CONCENTRATION_RISK,
        BEHAVIOURAL,
        MACRO_IMPACT,
        DIVERSIFICATION_STRATEGY,
        REBALANCING_ALLOCATION,
        FINANCE_THEORY,
        PORTFOLIO_PERFORMANCE,
    ]

    # If PORTFOLIO_PERFORMANCE is paired with one specific intent, drop the
    # generic match and use the specific intent.
    if PORTFOLIO_PERFORMANCE in matched:
        specific = [m for m in matched if m != PORTFOLIO_PERFORMANCE]
        if len(specific) == 1:
            return specific[0]

    for intent in priority:
        if intent in matched:
            return intent

    return MIXED


def top_k_for_intent(intent: str) -> int:
    """Return the recommended FAISS top_k for the given intent."""
    return INTENT_TOP_K.get(intent, 4)
