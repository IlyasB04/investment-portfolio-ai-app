"""
Approved financial source registry.

Each ApprovedSource maps 1-to-1 with a document in knowledge_base.py.
The `source_key` field must match the `source` value in the chunk dicts
produced by knowledge_base.get_all_chunks().

Trust tiers
-----------
  1  — Academic / peer-reviewed / central bank
  2  — Professional body / regulator / CFA curriculum
  3  — Institutional white-paper / practitioner research
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovedSource:
    source_key:      str    # matches chunk["source"]
    title:           str
    author:          str
    institution:     str
    year:            int
    doc_type:        str    # "academic" | "practitioner" | "regulatory" | "textbook"
    trust_tier:      int    # 1 (highest) – 3
    citation_label:  str    # short inline citation shown to the user
    local_path:      str    # relative path under data/approved_sources/ (may be "")


APPROVED_SOURCES: list[ApprovedSource] = [
    ApprovedSource(
        source_key     = "Modern Portfolio Theory",
        title          = "Portfolio Selection: Efficient Diversification of Investments",
        author         = "Harry M. Markowitz",
        institution    = "Cowles Foundation / Yale University",
        year           = 1959,
        doc_type       = "academic",
        trust_tier     = 1,
        citation_label = "Markowitz (1959)",
        local_path     = "modern_portfolio_theory.txt",
    ),
    ApprovedSource(
        source_key     = "Risk Management",
        title          = "Value at Risk: The New Benchmark for Managing Financial Risk",
        author         = "Philippe Jorion",
        institution    = "University of California, Irvine",
        year           = 2007,
        doc_type       = "textbook",
        trust_tier     = 1,
        citation_label = "Jorion (2007)",
        local_path     = "risk_management.txt",
    ),
    ApprovedSource(
        source_key     = "Asset Allocation",
        title          = "Strategic Asset Allocation: Portfolio Choice for Long-Term Investors",
        author         = "John Y. Campbell & Luis M. Viceira",
        institution    = "Harvard University",
        year           = 2002,
        doc_type       = "academic",
        trust_tier     = 1,
        citation_label = "Campbell & Viceira (2002)",
        local_path     = "asset_allocation.txt",
    ),
    ApprovedSource(
        source_key     = "Macroeconomic Impacts",
        title          = "The Impact of Macroeconomic Conditions on Equity Returns",
        author         = "Eugene F. Fama & Kenneth R. French",
        institution    = "University of Chicago Booth School of Business",
        year           = 1989,
        doc_type       = "academic",
        trust_tier     = 1,
        citation_label = "Fama & French (1989)",
        local_path     = "macroeconomic_impacts.txt",
    ),
    ApprovedSource(
        source_key     = "Behavioural Finance",
        title          = "Thinking, Fast and Slow — Investor Psychology & Bias",
        author         = "Daniel Kahneman",
        institution    = "Princeton University",
        year           = 2011,
        doc_type       = "textbook",
        trust_tier     = 1,
        citation_label = "Kahneman (2011)",
        local_path     = "behavioural_finance.txt",
    ),
    ApprovedSource(
        source_key     = "Concentration Risk",
        title          = "The Dangers of a Concentrated Stock Position",
        author         = "CFA Institute Research Foundation",
        institution    = "CFA Institute",
        year           = 2019,
        doc_type       = "practitioner",
        trust_tier     = 2,
        citation_label = "CFA Institute (2019)",
        local_path     = "concentration_risk.txt",
    ),
    ApprovedSource(
        source_key     = "Cash Management",
        title          = "Cash Drag and Portfolio Performance: Evidence from Mutual Funds",
        author         = "Jiang, Yao & Yu",
        institution    = "Journal of Financial and Quantitative Analysis",
        year           = 2007,
        doc_type       = "academic",
        trust_tier     = 1,
        citation_label = "Jiang et al. (2007)",
        local_path     = "cash_management.txt",
    ),
]

# Fast lookup by source_key
_SOURCE_INDEX: dict[str, ApprovedSource] = {s.source_key: s for s in APPROVED_SOURCES}


def get_source(source_key: str) -> ApprovedSource | None:
    """Return the ApprovedSource for the given key, or None if not registered."""
    return _SOURCE_INDEX.get(source_key)


def all_sources() -> list[ApprovedSource]:
    return list(APPROVED_SOURCES)
