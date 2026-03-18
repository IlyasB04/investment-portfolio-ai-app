"""
Financial knowledge base for the RAG assistant.

Seven topic documents covering the core theoretical pillars of portfolio
management.  get_all_chunks() returns every document pre-chunked into
overlapping passages of ~250 words for FAISS ingestion.

Chunking strategy
-----------------
  chunk_size  = 250 words
  overlap     = 50 words
  Split point = sentence boundary nearest to the chunk boundary

Documents
---------
  1. Modern Portfolio Theory & Diversification
  2. Risk Management & Position Sizing
  3. Asset Allocation Strategies
  4. Macroeconomic Impacts on Equity Markets
  5. Behavioural Finance & Cognitive Biases
  6. Concentration Risk & Sector Analysis
  7. Cash Management & Liquidity
"""

from __future__ import annotations

import re

# ── Knowledge documents ────────────────────────────────────────────────────────

_DOCUMENTS: list[dict] = [
    {
        "source": "Modern Portfolio Theory & Diversification",
        "text": """
Modern Portfolio Theory (MPT), introduced by Harry Markowitz in his landmark 1952 paper
"Portfolio Selection," fundamentally changed how investors think about risk and return.
The central insight is that the expected return of a portfolio is the weighted average
of the expected returns of its individual assets, but the risk of a portfolio is less
than the weighted average of the individual risks — provided the assets are not perfectly
correlated. This reduction in risk without a proportional reduction in expected return
is the mathematical foundation of diversification.

MPT distinguishes two types of risk. Systematic risk, also called market risk or
undiversifiable risk, affects the entire market and cannot be eliminated by holding
more assets. Examples include recessions, interest rate shifts, and geopolitical
events. Unsystematic risk, also called idiosyncratic or company-specific risk,
affects individual securities and can be substantially eliminated through
diversification. A portfolio of 20–30 uncorrelated stocks can reduce unsystematic
risk by roughly 90% compared with a single-stock portfolio.

The Efficient Frontier is the set of portfolios that offer the highest expected
return for each level of risk. Portfolios below the frontier are suboptimal — they
either take too much risk for their expected return or achieve too little return for
the risk they bear. Rational investors should choose portfolios on the frontier based
on their individual risk tolerance.

Correlation is the statistical measure of how two assets move relative to each other,
ranging from -1 (perfectly inversely correlated) to +1 (perfectly positively correlated).
Adding assets with low or negative correlation to an existing portfolio reduces
portfolio variance even if the new asset has higher standalone volatility. A classic
example is combining equities (high return, high vol) with government bonds (lower
return, lower vol, often negatively correlated to equities in risk-off environments).

The two-fund separation theorem states that any efficient portfolio can be constructed
as a combination of just two funds: the tangency portfolio (the optimal risky portfolio
on the efficient frontier) and the risk-free asset. This implies that all investors,
regardless of risk preference, should hold the same risky portfolio — the market
portfolio — and adjust their overall risk by varying the weight in the risk-free asset.
This is the theoretical underpinning of passive, index-based investing.

In practice, diversification means spreading investments across multiple asset classes
(equities, fixed income, real estate, commodities), geographies (domestic, international,
emerging markets), sectors (technology, healthcare, financials, energy), and market
capitalisations (large-cap, mid-cap, small-cap). Over-concentration in any single
dimension — even if that area has performed well — exposes the portfolio to unnecessary
idiosyncratic risk. A portfolio heavily weighted to a single sector or country is not
truly diversified even if it holds many individual securities within that sector.
"""
    },

    {
        "source": "Risk Management & Position Sizing",
        "text": """
Effective risk management is not about eliminating risk — that would also eliminate
return — but about taking deliberate, calibrated risks where the expected compensation
is adequate. Professional portfolio managers think of risk in multiple dimensions: the
probability of loss, the magnitude of loss, and the time horizon over which a loss
could occur.

Value at Risk (VaR) quantifies the maximum loss expected over a specified period with
a given confidence level. For example, a one-day 95% VaR of $10,000 means that on 95%
of trading days losses will be below $10,000, but on 5% of days they could exceed it.
VaR is useful but has well-known limitations: it says nothing about how large losses
in the tail can be, and it assumes normal return distributions that underweight
extreme events. Conditional VaR (CVaR or Expected Shortfall) addresses this by
measuring the average loss in the worst-case scenarios beyond the VaR threshold.

Beta measures a security's sensitivity to market movements. A beta of 1.5 means the
security historically moves 1.5% for every 1% move in the index. High-beta positions
amplify both gains and losses during market swings. Monitoring portfolio-weighted beta
gives a quick read on overall market sensitivity.

The Sharpe Ratio, (Rp - Rf) / σp, measures risk-adjusted return: how much excess
return (above the risk-free rate) is earned per unit of total risk (standard deviation).
Higher Sharpe ratios indicate more efficient risk-taking. The Sortino Ratio is a
refinement that uses only downside deviation in the denominator, penalising only
harmful volatility rather than all volatility.

Position sizing determines how much capital to allocate to each trade or security.
The Kelly Criterion, originally derived for betting, gives the theoretically optimal
fraction of capital to risk: f = (bp - q) / b, where b is the odds offered, p is the
probability of winning, and q = 1-p is the probability of losing. In practice,
investors use a fraction of the Kelly recommendation (often half-Kelly) because the
full Kelly can lead to extreme drawdowns when return assumptions are imprecise.

Fixed fractional position sizing — risking a constant percentage of total capital on
each position, typically 1–2% for professional traders — provides mechanical discipline.
It ensures no single position can cause catastrophic loss and forces smaller positions
as the portfolio loses value (reducing risk in drawdowns) and larger positions as it
grows.

Maximum drawdown — the peak-to-trough decline in portfolio value — is arguably the
most psychologically important risk metric, because it measures the actual pain an
investor would have experienced. Strategies with high average returns but severe
drawdowns are difficult to sustain because investors often capitulate near the bottom,
locking in losses. Understanding the historical maximum drawdown of any strategy
before committing capital is essential.
"""
    },

    {
        "source": "Asset Allocation Strategies",
        "text": """
Asset allocation is the process of dividing a portfolio among major asset classes —
equities, fixed income, cash, real assets, and alternatives — to match an investor's
return objectives, risk tolerance, and time horizon. Decades of empirical research,
including the seminal 1986 study by Brinson, Hood, and Beebower, found that strategic
asset allocation explains over 90% of the variability in portfolio returns over time,
dwarfing the contribution of security selection and market timing.

Strategic Asset Allocation (SAA) sets long-term target weights for each asset class
based on the investor's investment policy statement. A common example is the
traditional 60/40 portfolio — 60% global equities and 40% investment-grade bonds.
Historically, this combination delivered approximately 7–9% annualised nominal returns
with markedly lower volatility than a 100% equity portfolio, because bonds provided
income and often rallied when equities fell in recessions.

Tactical Asset Allocation (TAA) involves short-term deviations from SAA targets based
on market valuations, economic conditions, or momentum signals. A manager might
temporarily reduce equity exposure from 60% to 50% if equities appear overvalued
on cyclically adjusted P/E (CAPE) measures. TAA adds complexity and transaction costs;
evidence on consistent TAA outperformance is mixed.

Risk Parity is an alternative approach that allocates capital so each asset class
contributes equally to portfolio risk rather than capital. Because bonds have lower
volatility than equities, risk parity portfolios typically hold much larger bond
positions (often leveraged) to bring their risk contribution in line with equities.
Bridgewater's All Weather portfolio is a prominent example. Risk parity tends to
perform well in normal environments but can suffer during simultaneous equity and bond
sell-offs, as experienced in 2022.

Factor Investing targets systematic, well-documented return premiums: value (cheap vs
expensive stocks), size (small vs large cap), momentum (recent winners vs losers),
quality (high profitability and low leverage), and low volatility. Factor portfolios
are typically constructed to be diversified within each factor, and blending multiple
uncorrelated factors further reduces portfolio volatility.

Rebalancing is the periodic process of returning portfolio weights to their strategic
targets after market moves have caused drift. Calendar rebalancing (monthly, quarterly,
annually) is simple to implement. Threshold-based rebalancing — triggering when an
asset class drifts more than, say, 5% from its target — is more responsive to market
movements. Rebalancing mechanically enforces "buy low, sell high" discipline and
maintains the intended risk profile, but generates transaction costs and, in taxable
accounts, realised gains.
"""
    },

    {
        "source": "Macroeconomic Impacts on Equity Markets",
        "text": """
Equity markets do not operate in isolation — they are deeply intertwined with the
macroeconomic environment. Understanding macro forces helps investors anticipate sector
rotations, valuation regime shifts, and the changing attractiveness of equities relative
to other asset classes.

Interest rates, set by central banks like the Federal Reserve, are the single most
important macroeconomic variable for equity valuation. In the discounted cash flow
(DCF) framework, a stock's intrinsic value is the present value of its future cash
flows discounted at a rate that includes the risk-free rate. When the Fed raises rates,
the discount rate increases, reducing the present value of future cash flows — all else
equal, this is bearish for equities, particularly for long-duration growth stocks whose
cash flows are weighted further into the future. Conversely, rate cuts increase
valuations and historically spark equity rallies. The 2022 bear market, during which the
Fed raised rates from near-zero to over 5%, caused growth stocks to fall 60–80% as
their DCF valuations collapsed.

Inflation affects equities through multiple channels. Moderate inflation is generally
benign and often associated with strong nominal GDP growth. High, persistent inflation
erodes the real value of corporate earnings, increases input costs that compress margins,
and forces central banks to raise rates aggressively. Companies with pricing power —
the ability to pass cost increases to customers — outperform in inflationary environments.
Sectors with hard assets (energy, commodities, real estate) historically serve as partial
inflation hedges.

The economic cycle — expansion, peak, contraction, trough — strongly influences sector
performance. Classic sector rotation theory suggests that cyclical sectors (technology,
consumer discretionary, industrials) outperform in early expansions, while defensives
(utilities, consumer staples, healthcare) outperform late in the cycle and into
recessions. Energy tends to peak mid-cycle. Financials benefit from rising rates early
in tightening cycles but may struggle if a recession materialises and credit losses rise.

The yield curve — specifically the spread between long-term (10-year) and short-term
(2-year) Treasury yields — is a closely watched recession indicator. An inverted yield
curve, where short rates exceed long rates, has preceded every US recession over the
past 50 years with a typical lead time of 12–18 months. When the yield curve inverts,
it signals that markets expect the Fed to cut rates in the future — typically because
growth is expected to slow sharply.

Currency movements affect the earnings of multinational companies. A stronger US dollar
reduces the value of overseas revenues when translated back to dollars, creating an
earnings headwind for exporters and multinationals. A weaker dollar boosts translated
earnings. This is why a rising dollar environment is generally negative for the earnings
of large-cap US companies with significant international revenue, such as technology
and consumer goods multinationals.
"""
    },

    {
        "source": "Behavioural Finance & Cognitive Biases",
        "text": """
Behavioural finance studies how psychological biases and heuristics cause investors to
make systematic errors that deviate from the rational actor model assumed in classical
finance. Understanding these biases — and implementing rules to counteract them — is
one of the most actionable improvements an individual investor can make.

Loss Aversion, the cornerstone of Prospect Theory developed by Daniel Kahneman and
Amos Tversky, establishes that the psychological pain of a loss is approximately twice
as powerful as the pleasure of an equivalent gain. This asymmetry causes investors to
hold losing positions too long (hoping to break even) and sell winning positions too
early (locking in the comfort of a gain). The result is a "get-even" mentality that
systematically hurts long-term returns. Recognising loss aversion can help investors
follow rules that force them to cut losses at predetermined levels.

Overconfidence Bias leads investors to overestimate the precision of their knowledge
and the accuracy of their forecasts. Studies of self-reported stock-picking ability
consistently show that most investors believe they are above-average — statistically
impossible. Overconfidence manifests as excessive trading (active traders dramatically
underperform passive index investors on average, largely due to trading costs and poor
market timing), under-diversification (concentrating in a few names the investor
believes are superior), and insufficient hedging.

Confirmation Bias causes investors to seek out and disproportionately weight information
that confirms their existing beliefs while ignoring contradictory evidence. An investor
who is bullish on a stock will notice positive analyst reports and dismiss negative
ones. This bias can lead to holding onto deteriorating positions far too long. A
systematic antidote is to regularly steelman the bear case for any position: actively
construct the strongest possible argument against your thesis.

Herding occurs when investors follow the crowd rather than conducting independent
analysis. Herding amplifies bubbles and crashes — asset prices can deviate far from
fundamental value when mass psychology dominates. The dot-com bubble of 1999–2000
and the crypto manias of 2017 and 2021 are examples of herding driving assets to
extreme valuations before violent reversions to mean.

Anchoring causes investors to over-rely on the first piece of information encountered.
An investor who bought a stock at $100 per share may anchor to that price, perceiving
the stock as "cheap" at $70 even if its intrinsic value has fallen to $50. The purchase
price is irrelevant to the future outlook — what matters is the current price relative
to current intrinsic value. Mental Accounting treats money in different accounts
differently — for example, being willing to take more risk with "found money" (bonuses,
gambling winnings) than with earned savings, even though both are interchangeable.

Systematic, rules-based investing — pre-set rebalancing triggers, position sizing rules,
stop-loss levels, and diversification constraints — is the most reliable defence against
behavioural biases because it removes in-the-moment discretionary decisions.
"""
    },

    {
        "source": "Concentration Risk & Sector Analysis",
        "text": """
Concentration risk is the danger that a portfolio is excessively weighted to a small
number of positions, sectors, or correlated asset types, such that adverse developments
in any one of them cause disproportionate damage to the overall portfolio.

The Herfindahl-Hirschman Index (HHI) is the most widely used quantitative measure of
portfolio concentration. Calculated as the sum of the squared portfolio weights
(HHI = Σwi²), it ranges from near zero for highly diversified portfolios to 1.0 for
a single-asset portfolio. In portfolio analysis: HHI below 0.10 indicates strong
diversification, 0.10–0.18 indicates moderate concentration, 0.18–0.25 suggests
meaningful concentration risk, and above 0.25 signals high concentration requiring
attention. Unlike simple metrics like the number of holdings or the weight of the top
position, HHI captures the full distribution of weights in a single number.

Single-stock concentration is particularly dangerous because individual companies can
go to zero — through bankruptcy, fraud, or secular decline — in a way that a
diversified basket cannot. Enron, Lehman Brothers, and more recently many high-profile
tech stocks demonstrate how companies with large market caps and strong recent
performance can suffer catastrophic, rapid declines. As a rule of thumb, professional
risk managers rarely allow a single equity position to exceed 5–10% of a portfolio at
cost, and regularly review positions that have grown above this through appreciation.

Sector concentration is the aggregation of correlated risks. A portfolio of 20
technology stocks may appear diversified but all positions are exposed to the same
macro drivers: interest rates (technology is long-duration), regulatory risk
(antitrust, data privacy), and cyclical demand (enterprise and consumer spending on
tech products). When technology sold off in 2022, most tech-heavy portfolios fell
50–70% regardless of how many individual names they held.

The correlation structure within sectors is critical. Stocks within the same sector
tend to have correlations in the 0.5–0.8 range during normal periods and correlations
approaching 1.0 in crisis periods — a phenomenon called correlation breakdown or
"going to one in a crisis." This means the diversification benefit of holding multiple
names within a sector largely disappears exactly when it is most needed.

Geographic concentration — holding predominantly domestic equities — exposes portfolios
to country-specific political risk, currency risk, and economic cycles. The
outperformance of US equities over 2010–2023 led many investors to under-weight
international exposure, creating structural concentration that may reverse if the US
dollar weakens, US growth slows, or valuations revert toward international averages.
MSCI estimates that non-US equities represent approximately 55% of global market
capitalisation — a diversified global portfolio should reflect this.
"""
    },

    {
        "source": "Cash Management & Liquidity in Portfolios",
        "text": """
Cash — defined broadly to include money market funds, Treasury bills, and short-dated
investment-grade bonds — plays multiple important roles in a portfolio beyond simply
being "money waiting to be invested."

The opportunity cost argument against holding cash is well-founded in the long run:
over any 10-year period, equities have historically outperformed cash by a substantial
margin. This is why investment dogma often dismisses cash as a drag and encourages
full investment at all times. However, this view ignores cash's optionality value —
the flexibility to deploy capital at attractive valuations during market dislocations
— and its role in managing drawdowns and psychological stability.

Liquidity management addresses the ability to meet obligations without forced selling
of long-term positions at unfavourable prices. Even a well-constructed portfolio can be
impaired if illiquid positions must be sold to meet short-term needs. A common rule is
to hold 6–12 months of living expenses in liquid form outside the investment portfolio,
ensuring no forced selling during market downturns.

The "dry powder" concept — maintaining a tactical cash reserve to deploy during
market sell-offs — is a legitimate strategy for investors with conviction in long-term
equity investing but who wish to benefit from periodic dislocations. Drawdown-triggered
deployment rules (e.g., moving 5% from cash to equities each time the market falls
10%) remove the psychological difficulty of buying during panics and provide a
systematic framework for capitalising on volatility.

Cash drag over long investment horizons is real and should not be dismissed. A 10%
cash allocation in a portfolio earning 8% annual equity returns costs approximately
80 basis points per year in foregone return relative to full investment. Over 20 years,
this compounds to a meaningful wealth difference. Investors with no specific deployment
plan or liquidity need should keep cash exposure minimal.

Since 2022, cash has recovered its income-generating role. Short-duration T-bills
yielding 4–5% provide genuine competition for low-risk equity income and bonds in a
way that was absent during the near-zero interest rate era (2009–2022). This changes
the portfolio construction calculus: cash and T-bills can now replace some bond
exposure and reduce overall portfolio duration risk while maintaining income generation.

The optimal cash allocation is not static but depends on: the investor's time horizon,
the level of interest rates on cash alternatives, current equity valuations (CAPE),
and the investor's capacity to deploy capital quickly when dislocations arise. A
systematic framework beats emotional decision-making — predetermined rules for when to
build and deploy cash reserves eliminate the temptation to hold too much cash when
markets are rising or too little when they fall.
"""
    },
]


# ── Chunker ────────────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving trailing whitespace."""
    # Simple but robust: split on ". " / "! " / "? " followed by a capital letter.
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _chunk_text(text: str, chunk_words: int = 250, overlap_words: int = 50) -> list[str]:
    """
    Split `text` into overlapping chunks of approximately `chunk_words` words.

    Strategy:
      1. Split into sentences.
      2. Greedily fill chunks until `chunk_words` is reached.
      3. Start the next chunk `overlap_words` before the current boundary.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    # Convert to (sentence, word_count) pairs
    pairs = [(s, len(s.split())) for s in sentences]

    chunks: list[str] = []
    start_idx = 0

    while start_idx < len(pairs):
        current_words = 0
        end_idx = start_idx

        # Accumulate sentences until we hit chunk_words
        while end_idx < len(pairs) and current_words < chunk_words:
            current_words += pairs[end_idx][1]
            end_idx += 1

        chunk_text = " ".join(s for s, _ in pairs[start_idx:end_idx])
        chunks.append(chunk_text)

        if end_idx >= len(pairs):
            break

        # Backtrack by overlap_words to create the overlap window
        overlap_count = 0
        backtrack = end_idx - 1
        while backtrack > start_idx and overlap_count < overlap_words:
            overlap_count += pairs[backtrack][1]
            backtrack -= 1
        start_idx = backtrack + 1

        # Guard against infinite loop (e.g., a single enormous sentence)
        if start_idx == 0:
            break

    return chunks


# ── Public API ─────────────────────────────────────────────────────────────────

def get_all_chunks() -> list[dict]:
    """
    Return every document chunked into overlapping passages.

    Each element:
      {"text": str, "source": str, "chunk_id": int, "word_count": int}
    """
    all_chunks: list[dict] = []
    chunk_id = 0

    for doc in _DOCUMENTS:
        raw = doc["text"]
        source = doc["source"]
        text_chunks = _chunk_text(raw, chunk_words=250, overlap_words=50)

        for chunk in text_chunks:
            all_chunks.append({
                "chunk_id": chunk_id,
                "source": source,
                "text": chunk,
                "word_count": len(chunk.split()),
            })
            chunk_id += 1

    return all_chunks


def list_sources() -> list[str]:
    """Return the unique source names in the knowledge base."""
    return [d["source"] for d in _DOCUMENTS]
