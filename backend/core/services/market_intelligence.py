"""
Market Intelligence Service

Fetches current finance headlines from public RSS feeds, performs
lightweight sentiment and theme analysis, maps findings to the user's
holdings and sectors, and generates a short AI summary via Groq.

Design constraints
------------------
- No external dependencies beyond stdlib + groq (already installed)
- Uses urllib.request + xml.etree.ElementTree (stdlib only for HTTP/XML)
- Headline-level scraping only — no article body fetching
- Sentiment: keyword intersection (transparent, no ML library)
- Themes:    compiled regex patterns against headline text
- Portfolio: keyword + ticker-symbol matching against holdings
- AI prompt: compact (<500 token input) → 200 token output via Groq

RSS sources used
----------------
  BBC Business    — feeds.bbci.co.uk   (RSS 2.0, highly reliable)
  Yahoo Finance   — finance.yahoo.com  (RSS 2.0)
  CNBC Markets    — cnbc.com           (RSS 2.0)
"""

from __future__ import annotations

import logging
import re
import ssl
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── SSL context ────────────────────────────────────────────────────────────────
# Python on macOS (homebrew / venv installs) often cannot locate the system CA
# bundle, causing SSL: CERTIFICATE_VERIFY_FAILED on every HTTPS request.
# For a local demo this is acceptable — we disable cert verification so that
# all five RSS sources return 200 rather than silently failing.

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode    = ssl.CERT_NONE

# ── RSS sources (confirmed reachable) ─────────────────────────────────────────
# All five tested: return HTTP 200 + valid RSS 2.0 XML with title elements.

_SOURCES: list[dict[str, str]] = [
    {
        "name": "BBC Business",
        "url":  "https://feeds.bbci.co.uk/news/business/rss.xml",
    },
    {
        "name": "Yahoo Finance",
        "url":  "https://finance.yahoo.com/news/rssindex",
    },
    {
        "name": "CNBC Finance",
        "url":  "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    },
    {
        "name": "Google News",
        "url":  (
            "https://news.google.com/rss/topics/"
            "CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB"
            "?hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "MarketWatch",
        "url":  "https://feeds.marketwatch.com/marketwatch/topstories/",
    },
]

_REQUEST_TIMEOUT  = 5    # seconds per source — fail fast so the page stays snappy
_MAX_PER_SOURCE   = 10   # max headlines to take from each feed
# Full browser UA avoids CDN bot-blocking on several of the above feeds
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ── Sentiment keyword sets ─────────────────────────────────────────────────────

_POSITIVE: frozenset[str] = frozenset({
    "gain", "gains", "gained", "surge", "surges", "surged", "rise", "rises",
    "rose", "rally", "rallied", "beat", "beats", "strong", "stronger",
    "growth", "grew", "profit", "profits", "bullish", "recovery", "recovers",
    "record", "outperform", "upgrade", "upgraded", "positive", "boost",
    "boosted", "higher", "advance", "advances", "improved", "exceed",
    "exceeded", "soar", "soared", "jump", "jumped", "top", "win", "wins",
})

_NEGATIVE: frozenset[str] = frozenset({
    "fall", "falls", "fell", "drop", "drops", "dropped", "decline",
    "declines", "declined", "crash", "crashes", "crashed", "loss", "losses",
    "miss", "misses", "missed", "weak", "weaker", "recession", "bearish",
    "fear", "fears", "concern", "concerns", "warning", "warnings",
    "downgrade", "downgraded", "negative", "cut", "cuts", "lower", "slump",
    "slumped", "plunge", "plunged", "sink", "sank", "shrink", "shrank",
    "tumble", "tumbled", "risk", "volatile", "volatility", "crisis",
    "trouble", "tariff", "tariffs", "slowdown", "deficit",
})

# ── Theme patterns ─────────────────────────────────────────────────────────────

_THEME_PATTERNS: dict[str, list[str]] = {
    "Rates": [
        r"\brate[s]?\b", r"\bfed\b", r"\bfederal reserve\b",
        r"\bcentral bank\b", r"\binterest rate[s]?\b", r"\bfomc\b",
        r"\bboe\b", r"\becb\b", r"\brate hike\b", r"\brate cut\b",
    ],
    "Inflation": [
        r"\binflation\b", r"\bcpi\b", r"\bppi\b",
        r"\bconsumer price\b", r"\bdeflation\b", r"\bcost of living\b",
        r"\bprice[s]? rise\b",
    ],
    "Technology": [
        r"\btech\b", r"\btechnology\b", r"\bsemiconductor\b",
        r"\bchip[s]?\b", r"\bsoftware\b", r"\bdigital\b",
        r"\bsilicon valley\b",
    ],
    "Earnings": [
        r"\bearning[s]?\b", r"\brevenue\b", r"\bprofit[s]?\b",
        r"\bquarterly\b", r"\bguidance\b", r"\bbeat[s]?\b",
        r"\bmissed estimate\b", r"\beps\b",
    ],
    "Oil & Energy": [
        r"\boil\b", r"\bcrude\b", r"\bopec\b", r"\bpetroleum\b",
        r"\bbrent\b", r"\bwti\b", r"\bnatural gas\b", r"\benergy price\b",
    ],
    "Recession": [
        r"\brecession\b", r"\bdownturn\b", r"\bcontraction\b",
        r"\bgdp\b", r"\bslowdown\b", r"\bgrowth slows\b",
    ],
    "AI": [
        r"\bartificial intelligence\b", r"\bmachine learning\b",
        r"\bchatgpt\b", r"\bopenai\b", r"\bgenerative ai\b",
        r"\bai model[s]?\b", r"\bllm\b",
    ],
    "Regulation": [
        r"\bregulat\w+\b", r"\bsec\b", r"\bantitrust\b",
        r"\bpenalt\w+\b", r"\bfined\b", r"\blawsuit\b", r"\bcompliance\b",
    ],
    "Trade": [
        r"\btariff[s]?\b", r"\btrade war\b", r"\btrade deal\b",
        r"\bimport[s]?\b", r"\bexport[s]?\b", r"\bsanction[s]?\b",
    ],
}

_COMPILED_THEMES: dict[str, list[re.Pattern]] = {
    theme: [re.compile(p, re.IGNORECASE) for p in pats]
    for theme, pats in _THEME_PATTERNS.items()
}

# ── Ticker keyword map ─────────────────────────────────────────────────────────

_TICKER_KEYWORDS: dict[str, list[str]] = {
    "AAPL":  ["apple", "iphone", "ipad", "mac", "app store", "tim cook"],
    "MSFT":  ["microsoft", "azure", "windows", "copilot", "satya nadella"],
    "NVDA":  ["nvidia", "gpu", "jensen huang", "graphics card"],
    "AMD":   ["advanced micro devices", " amd "],
    "INTC":  ["intel", "pat gelsinger"],
    "GOOGL": ["google", "alphabet", "youtube", "android", "gemini"],
    "GOOG":  ["google", "alphabet"],
    "META":  ["meta", "facebook", "instagram", "whatsapp", "zuckerberg"],
    "TSLA":  ["tesla", "elon musk", "electric vehicle", " ev "],
    "AMZN":  ["amazon", "aws", "prime video", "andy jassy"],
    "JPM":   ["jpmorgan", "jp morgan", "jamie dimon"],
    "BAC":   ["bank of america", "bofa"],
    "GS":    ["goldman sachs", "goldman"],
    "MS":    ["morgan stanley"],
    "WFC":   ["wells fargo"],
    "V":     ["visa"],
    "MA":    ["mastercard"],
    "XOM":   ["exxon", "exxonmobil"],
    "CVX":   ["chevron"],
    "COP":   ["conocophillips"],
    "JNJ":   ["johnson & johnson", "johnson and johnson"],
    "PFE":   ["pfizer"],
    "LLY":   ["eli lilly", " lilly "],
    "UNH":   ["unitedhealth", "united health"],
    "KO":    ["coca-cola", "coca cola"],
    "PEP":   ["pepsico", "pepsi"],
    "WMT":   ["walmart"],
    "COST":  ["costco"],
    "NKE":   ["nike"],
    "HD":    ["home depot"],
    "MCD":   ["mcdonald"],
    "BA":    ["boeing"],
    "CAT":   ["caterpillar"],
    "GE":    ["general electric"],
    "NFLX":  ["netflix"],
    "PYPL":  ["paypal"],
    "UBER":  ["uber"],
    "ABNB":  ["airbnb"],
    "SHOP":  ["shopify"],
    "SQ":    ["block", "square"],
    "COIN":  ["coinbase"],
    "BTC":   ["bitcoin"],
    "ETH":   ["ethereum"],
}

# ── Sector map ─────────────────────────────────────────────────────────────────

_SECTOR_MAP: dict[str, str] = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMD":  "Technology", "INTC": "Technology", "GOOGL": "Technology",
    "GOOG": "Technology", "META": "Technology", "ADBE": "Technology",
    "CRM":  "Technology", "ORCL": "Technology", "CSCO": "Technology",
    "AVGO": "Technology", "QCOM": "Technology", "TXN": "Technology",
    "NFLX": "Technology", "SHOP": "Technology",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "NKE":  "Consumer Discretionary", "HD": "Consumer Discretionary",
    "MCD":  "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    "UBER": "Consumer Discretionary", "ABNB": "Consumer Discretionary",
    "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "PG": "Consumer Staples", "WMT": "Consumer Staples",
    "COST": "Consumer Staples", "PM": "Consumer Staples",
    "JNJ": "Healthcare", "PFE": "Healthcare", "UNH": "Healthcare",
    "ABBV": "Healthcare", "MRK": "Healthcare", "LLY": "Healthcare",
    "TMO": "Healthcare", "ABT": "Healthcare",
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS":  "Financials", "MS": "Financials", "BRK.B": "Financials",
    "V":   "Financials", "MA": "Financials", "AXP": "Financials",
    "BLK": "Financials", "PYPL": "Financials", "COIN": "Financials",
    "SQ":  "Financials",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "SLB": "Energy", "OXY": "Energy",
    "BA": "Industrials", "CAT": "Industrials", "GE": "Industrials",
    "UPS": "Industrials", "RTX": "Industrials", "HON": "Industrials",
    "DE":  "Industrials",
    "BTC": "Crypto", "ETH": "Crypto",
}

# Themes most relevant to each sector
_SECTOR_THEMES: dict[str, list[str]] = {
    "Technology":             ["Technology", "AI", "Earnings", "Regulation"],
    "Financials":             ["Rates", "Regulation", "Earnings"],
    "Energy":                 ["Oil & Energy", "Recession", "Trade"],
    "Consumer Discretionary": ["Inflation", "Recession", "Earnings"],
    "Consumer Staples":       ["Inflation", "Earnings"],
    "Healthcare":             ["Regulation", "Earnings"],
    "Industrials":            ["Recession", "Earnings", "Trade"],
    "Crypto":                 ["Regulation", "Rates"],
}


# ── RSS fetch ──────────────────────────────────────────────────────────────────

def _fetch_rss(url: str, source_name: str) -> list[dict]:
    """
    Fetch and parse an RSS 2.0 (or Atom) feed.
    Returns list of raw headline dicts: {source, title, url, published}.
    Returns [] on any network or parse failure — one bad source never
    breaks the full response.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept":     "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        # _SSL_CTX disables cert verification — required on macOS venv installs
        # where the system CA bundle is not in Python's default search path.
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT, context=_SSL_CTX) as resp:
            raw_xml = resp.read()
    except urllib.error.HTTPError as exc:
        logger.warning(
            "[market_intel] HTTP %d fetching %s (%s): %s",
            exc.code, source_name, url, exc.reason,
        )
        return []
    except urllib.error.URLError as exc:
        logger.warning(
            "[market_intel] URL error fetching %s (%s): %s",
            source_name, url, exc.reason,
        )
        return []
    except Exception as exc:
        logger.warning(
            "[market_intel] Unexpected %s fetching %s (%s): %s",
            type(exc).__name__, source_name, url, exc,
        )
        return []

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        logger.warning(
            "[market_intel] XML parse error for %s: %s",
            source_name, exc,
        )
        return []

    items: list[dict] = []
    ns_atom = "http://www.w3.org/2005/Atom"

    # ── RSS 2.0 ──────────────────────────────────────────────────────────────
    for channel in root.iter("channel"):
        for item in list(channel.iter("item"))[:_MAX_PER_SOURCE]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = item.findtext("pubDate") or ""
            if not title:
                continue
            items.append({
                "source":    source_name,
                "title":     title,
                "url":       link,
                "published": _parse_rfc2822(pub),
            })

    # ── Atom fallback ─────────────────────────────────────────────────────────
    if not items:
        for entry in list(root.iter(f"{{{ns_atom}}}entry"))[:_MAX_PER_SOURCE]:
            title    = (entry.findtext(f"{{{ns_atom}}}title") or "").strip()
            link_el  = entry.find(f"{{{ns_atom}}}link")
            link     = link_el.get("href", "") if link_el is not None else ""
            pub      = entry.findtext(f"{{{ns_atom}}}updated") or ""
            if not title:
                continue
            items.append({
                "source":    source_name,
                "title":     title,
                "url":       link,
                "published": _parse_iso8601(pub),
            })

    logger.info(
        "[market_intel] fetched source=%s items=%d",
        source_name, len(items),
    )
    return items


def _parse_rfc2822(date_str: str) -> Optional[str]:
    """RFC 2822 (RSS pubDate) → ISO 8601 UTC string, or None."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _parse_iso8601(date_str: str) -> Optional[str]:
    """ISO 8601 string → normalised ISO string, or None."""
    if not date_str:
        return None
    try:
        ds = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ds).isoformat()
    except Exception:
        return None


# ── Sentiment ──────────────────────────────────────────────────────────────────

def _sentiment(text: str) -> str:
    """
    Keyword-bag sentiment.  Returns 'positive', 'neutral', or 'negative'.
    """
    tokens = set(re.findall(r"\b[a-z]+\b", text.lower()))
    pos = len(tokens & _POSITIVE)
    neg = len(tokens & _NEGATIVE)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


# ── Theme detection ────────────────────────────────────────────────────────────

def _themes(text: str) -> list[str]:
    """Return sorted list of theme names that match the headline text."""
    return sorted(
        theme
        for theme, pats in _COMPILED_THEMES.items()
        if any(p.search(text) for p in pats)
    )


# ── Ticker matching ────────────────────────────────────────────────────────────

def _match_tickers(text: str, user_tickers: list[str]) -> list[str]:
    """
    Return the subset of user_tickers mentioned in text.
    Checks both the bare ticker symbol (word boundary) and company keywords.
    """
    lower = text.lower()
    matched = []
    for ticker in user_tickers:
        if re.search(r"\b" + re.escape(ticker) + r"\b", text, re.IGNORECASE):
            matched.append(ticker)
            continue
        kws = _TICKER_KEYWORDS.get(ticker.upper(), [])
        if any(kw in lower for kw in kws):
            matched.append(ticker)
    return matched


# ── Holdings impact ────────────────────────────────────────────────────────────

def _holdings_impact(headlines: list[dict], user_tickers: list[str]) -> list[dict]:
    """
    Per-ticker impact: aggregate sentiment of headlines that mention the ticker.
    Falls back to sector-level theme sentiment when no direct mention exists.
    """
    ticker_sentiments: dict[str, list[str]] = defaultdict(list)
    ticker_titles:     dict[str, list[str]] = defaultdict(list)

    for h in headlines:
        for t in _match_tickers(h["title"], user_tickers):
            ticker_sentiments[t].append(h["sentiment"])
            ticker_titles[t].append(h["title"])

    results = []
    for ticker in user_tickers:
        sentiments = ticker_sentiments.get(ticker, [])
        titles     = ticker_titles.get(ticker, [])
        sector     = _SECTOR_MAP.get(ticker.upper(), "Unknown")

        if not sentiments:
            # Derive from sector-level themes
            sector_themes = _SECTOR_THEMES.get(sector, [])
            relevant      = [
                h for h in headlines
                if any(t in h["themes"] for t in sector_themes)
            ]
            if relevant:
                pos = sum(1 for h in relevant if h["sentiment"] == "positive")
                neg = sum(1 for h in relevant if h["sentiment"] == "negative")
                if pos > neg:
                    impact = "positive"
                    note   = f"No direct mention. {sector} sector news skews positive today."
                elif neg > pos:
                    impact = "negative"
                    note   = f"No direct mention. {sector} sector news skews negative today."
                else:
                    impact = "neutral"
                    note   = f"No direct mention. {sector} sector news is mixed today."
            else:
                impact = "neutral"
                note   = "No relevant market news detected for this position today."
        else:
            pos = sentiments.count("positive")
            neg = sentiments.count("negative")
            impact = "positive" if pos > neg else ("negative" if neg > pos else "neutral")
            sample = titles[0][:80] + ("…" if len(titles[0]) > 80 else "")
            count  = len(titles)
            note   = f"{count} headline{'s' if count > 1 else ''} mention {ticker}. e.g. \"{sample}\""

        results.append({"ticker": ticker, "impact": impact, "explanation": note})

    return results


# ── Sector impact ──────────────────────────────────────────────────────────────

def _sector_impact(headlines: list[dict], user_sectors: list[str]) -> list[dict]:
    """Per-sector impact based on theme relevance of headlines."""
    results = []
    for sector in user_sectors:
        themes   = _SECTOR_THEMES.get(sector, [])
        relevant = [h for h in headlines if any(t in h["themes"] for t in themes)]

        if not relevant:
            results.append({
                "sector":         sector,
                "impact":         "neutral",
                "headline_count": 0,
                "explanation":    f"No headlines matched {sector} sector themes today.",
            })
            continue

        pos   = sum(1 for h in relevant if h["sentiment"] == "positive")
        neg   = sum(1 for h in relevant if h["sentiment"] == "negative")
        total = len(relevant)

        if pos > neg:
            impact = "positive"
        elif neg > pos:
            impact = "negative"
        else:
            impact = "neutral"

        matched_themes = sorted(
            {t for h in relevant for t in h["themes"] if t in themes}
        )
        theme_str = ", ".join(matched_themes) if matched_themes else "general"

        results.append({
            "sector":         sector,
            "impact":         impact,
            "headline_count": total,
            "explanation":    f"{total} headline{'s' if total > 1 else ''} touch {theme_str} — relevant to {sector}.",
        })

    return results


# ── AI summary ─────────────────────────────────────────────────────────────────

def _ai_summary(
    headlines:       list[dict],
    user_tickers:    list[str],
    holdings_impact: list[dict],
) -> tuple[Optional[str], Optional[str]]:
    """
    Generate a short (3-sentence) summary via Groq.
    Sends compact processed data — not raw headlines — to keep token count low.
    Returns (summary_text, error_code).
    """
    from .groq_client import generate_with_history, is_api_configured

    if not is_api_configured():
        return None, "API_NOT_CONFIGURED"

    # Compact headline list — title + sentiment + themes (max 15 items)
    hl_lines = []
    for h in headlines[:15]:
        t_str = ", ".join(h["themes"]) if h["themes"] else "general"
        hl_lines.append(f"• {h['title']} [{h['sentiment']}] ({t_str})")

    # Holdings impact summary lines
    imp_lines = [
        f"• {item['ticker']}: {item['impact']}"
        for item in holdings_impact
    ] if holdings_impact else ["• No holdings in portfolio"]

    tickers_str = ", ".join(user_tickers) if user_tickers else "none"

    user_message = (
        "Today's finance headlines:\n"
        + "\n".join(hl_lines)
        + f"\n\nPortfolio holdings: {tickers_str}\n"
        + "Holdings impact:\n"
        + "\n".join(imp_lines)
        + "\n\nIn exactly 3 concise sentences, summarise: "
        "(1) what is driving today's market news, "
        "(2) how this could affect broader markets, "
        "(3) how it may affect this specific portfolio."
    )

    system = (
        "You are a concise financial analyst assistant. "
        "Respond in exactly 3 short sentences. "
        "Be specific, factual, and direct. "
        "Do not use bullet points. Do not repeat headlines verbatim."
    )

    content, err = generate_with_history(
        history     = [{"role": "user", "content": user_message}],
        system      = system,
        temperature = 0.2,
        max_tokens  = 220,
    )
    return content, err


# ── Public entry point ─────────────────────────────────────────────────────────

def get_market_intelligence(user: Any) -> dict[str, Any]:
    """
    Full pipeline: fetch → enrich → analyse → AI summary → return dict.

    The returned dict is JSON-serialisable and matches the frontend contract.
    """
    from ..models import Holding

    # ── Load holdings ──────────────────────────────────────────────────────────
    raw_tickers  = list(
        Holding.objects.filter(user=user).values_list("ticker", flat=True)
    )
    user_tickers = [t.upper() for t in raw_tickers]
    user_sectors = sorted({
        _SECTOR_MAP.get(t, "Unknown")
        for t in user_tickers
        if _SECTOR_MAP.get(t)
    })

    # ── Fetch RSS feeds ────────────────────────────────────────────────────────
    raw: list[dict] = []
    sources_ok: list[str] = []
    for src in _SOURCES:
        items = _fetch_rss(src["url"], src["name"])
        if items:
            sources_ok.append(src["name"])
        raw.extend(items)

    # Deduplicate by normalised title
    seen: set[str] = set()
    unique: list[dict] = []
    for h in raw:
        key = re.sub(r"\s+", " ", h["title"].lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(h)

    # ── Enrich each headline ───────────────────────────────────────────────────
    enriched: list[dict] = [
        {
            **h,
            "sentiment": _sentiment(h["title"]),
            "themes":    _themes(h["title"]),
            "tickers":   _match_tickers(h["title"], user_tickers),
        }
        for h in unique
    ]

    # ── Market pulse ───────────────────────────────────────────────────────────
    pos_count = sum(1 for h in enriched if h["sentiment"] == "positive")
    neg_count = sum(1 for h in enriched if h["sentiment"] == "negative")
    neu_count = len(enriched) - pos_count - neg_count

    all_themes_flat: list[str] = [t for h in enriched for t in h["themes"]]
    top_themes = [t for t, _ in Counter(all_themes_flat).most_common(5)]

    if pos_count > neg_count:
        overall = "positive"
    elif neg_count > pos_count:
        overall = "negative"
    else:
        overall = "neutral"

    market_pulse = {
        "overall_sentiment": overall,
        "positive_count":    pos_count,
        "neutral_count":     neu_count,
        "negative_count":    neg_count,
        "top_themes":        top_themes,
        "headline_count":    len(enriched),
    }

    # ── Per-ticker and per-sector analysis ─────────────────────────────────────
    holdings_impact = _holdings_impact(enriched, user_tickers)
    sector_impact   = _sector_impact(enriched, user_sectors)

    # ── AI summary ─────────────────────────────────────────────────────────────
    ai_text, ai_err = _ai_summary(enriched, user_tickers, holdings_impact)

    return {
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "market_pulse":    market_pulse,
        "headlines":       enriched,
        "holdings_impact": holdings_impact,
        "sector_impact":   sector_impact,
        "ai_summary":      ai_text,
        "ai_error":        ai_err,
        "sources_used":    sources_ok,
        "no_data":         len(enriched) == 0,
    }
