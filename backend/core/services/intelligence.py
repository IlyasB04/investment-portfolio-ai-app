"""
Portfolio Intelligence Service — production local RAG agent.

Architecture
------------
  Ollama is REQUIRED. If the local model is unavailable the pipeline
  immediately returns a structured LOCAL_MODEL_UNAVAILABLE error.
  The deterministic analytics engine (analytics.py + reasoning.py) provides
  rich inputs TO the LLM — it is not the fallback answer generator.

Pipeline steps
--------------
  0.  Ollama health check              → abort immediately if unavailable
  1.  Build PortfolioContext           (analytics.py)
  2.  Classify question intent         (intent.py)
  3.  Retrieve relevant chunks         (vector_store.py, top_k = f(intent))
  4.  Run deterministic reasoning      (reasoning.py)
  5.  Load / create Conversation       (models.Conversation)
  6.  Inject conversation memory       (conversation.memory_summary)
  7.  Compute confidence score
  8.  Build intent-aware analyst prompt
  9.  Call Ollama local LLM
  10. Persist messages + update memory summary + audit log

Intent-aware prompts
---------------------
  Each intent routes to a different analyst persona and context weighting:
    portfolio_performance    → portfolio review analyst, P&L focus
    concentration_risk       → risk analyst, HHI and sector exposure
    diversification_strategy → allocation strategist, correlation and spread
    macro_impact             → macro-aware analyst, rate/inflation sensitivity
    finance_theory           → investment strategist, academic + applied
    behavioural              → behavioural finance coach, psychology-aware
    rebalancing_allocation   → portfolio construction advisor
    mixed                    → generalist portfolio analyst

Memory summarisation
---------------------
  After each assistant reply the conversation.memory_summary is updated
  using a compact LLM summarisation call so follow-up questions
  ("Why?" / "What about AAPL specifically?") resolve correctly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

MEMORY_TURNS     = 4        # recent turns loaded into prompt history (8 messages)
MAX_QUESTION_LEN = 2_000
OLLAMA_MODEL     = "mistral"

MODEL_UNAVAILABLE_ERROR = "LOCAL_MODEL_UNAVAILABLE"
MODEL_TIMEOUT_ERROR     = "MODEL_TIMEOUT"
GENERATION_ERROR        = "GENERATION_ERROR"


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class IntelligenceResult:
    answer:               str
    sources:              list[dict]
    confidence:           str                # "high" | "medium" | "low"
    reasoning_flags:      list[dict]
    portfolio_snapshot:   dict
    conversation_id:      str                # UUID string
    conversation_title:   str
    model_used:           str
    retrieval_used:       bool
    intent:               str
    memory_summary_used:  bool
    error:                Optional[str] = None   # MODEL_UNAVAILABLE_ERROR / MODEL_TIMEOUT_ERROR / GENERATION_ERROR / None
    audit_id:             Optional[int] = None


# ── Confidence scoring ─────────────────────────────────────────────────────────

def compute_confidence(
    has_portfolio:    bool,
    retrieval_scores: list[float],
    intent:           str,
) -> str:
    from .intent import FINANCE_THEORY, MACRO_IMPACT, DIVERSIFICATION_STRATEGY

    top_score = max(retrieval_scores, default=0.0)

    # Theory/macro/diversification: retrieval quality is the primary signal
    if intent in (FINANCE_THEORY, MACRO_IMPACT, DIVERSIFICATION_STRATEGY):
        if top_score >= 0.45:
            return "high"
        if top_score >= 0.28:
            return "medium"
        return "low"

    # Portfolio-centric intents: having live data is essential
    if has_portfolio and top_score >= 0.40:
        return "high"
    if has_portfolio:
        return "medium"
    return "low"


# ── Memory summary ─────────────────────────────────────────────────────────────

def _update_memory_summary(
    conversation,
    question: str,
    answer:   str,
    intent:   str,
    flags:    list,
    tickers:  list[str],
) -> None:
    """
    Update conversation.memory_summary with a deterministic bullet after each turn.

    Deterministic-only (no second Ollama call) — keeps one generation per message.
    """
    flag_names = [f.flag_id for f in flags] if flags else []
    ticker_str = ", ".join(tickers[:5]) if tickers else "none"
    flag_str   = ", ".join(flag_names[:3]) if flag_names else "none"

    topic  = question.strip().rstrip("?").split(".")[0][:70]
    bullet = f"{topic} [{intent}] — tickers: {ticker_str}, flags: {flag_str}"

    existing = conversation.memory_summary or ""
    entries  = [e for e in existing.split("\n• ") if e.strip()]
    entries  = entries[-4:]   # rolling window of last 4 turns
    entries.append(bullet)
    conversation.memory_summary = "• " + "\n• ".join(entries)
    conversation.last_question  = question[:500]
    conversation.save(update_fields=["memory_summary", "last_question", "updated_at"])


def _memory_prompt_block(conversation) -> str:
    if not conversation.memory_summary:
        return ""
    return (
        "CONVERSATION MEMORY (previous turns in this session):\n"
        + conversation.memory_summary
        + "\n\n"
    )


# ── Conversation helpers ───────────────────────────────────────────────────────

def _get_or_create_conversation(user, conversation_id: str | None):
    from ..models import Conversation
    if conversation_id:
        try:
            return Conversation.objects.get(pk=conversation_id, user=user)
        except (Conversation.DoesNotExist, ValueError):
            pass
    return Conversation.objects.create(user=user)


def _auto_title(question: str) -> str:
    """Generate a short conversation title from the first question."""
    q = question.strip().rstrip("?.")
    words = q.split()
    title = " ".join(words[:8])
    return title[:80] if title else "Portfolio Analysis"


def _load_history(conversation) -> list[dict]:
    from ..models import ConversationMessage
    msgs = list(
        ConversationMessage.objects
        .filter(conversation=conversation)
        .order_by("-created_at")[: MEMORY_TURNS * 2]
    )
    msgs.reverse()
    return [{"role": m.role, "content": m.content} for m in msgs]


def _persist_turn(
    conversation,
    question:       str,
    answer:         str,
    confidence:     str,
    intent:         str,
    model_used:     str,
    retrieval_used: bool,
    flags:          list,
    sources:        list[dict],
) -> None:
    from ..models import ConversationMessage
    ConversationMessage.objects.create(
        conversation = conversation,
        role         = ConversationMessage.Role.USER,
        content      = question,
    )
    ConversationMessage.objects.create(
        conversation         = conversation,
        role                 = ConversationMessage.Role.ASSISTANT,
        content              = answer,
        confidence           = confidence,
        intent               = intent,
        model_used           = model_used,
        retrieval_used       = retrieval_used,
        reasoning_flags_json = [f.to_dict() for f in flags],
        sources_json         = sources,
    )
    conversation.save(update_fields=["updated_at"])


# ── Audit log ──────────────────────────────────────────────────────────────────

def _write_audit_log(
    *,
    user,
    question:           str,
    answer:             str,
    chunks:             list[dict],
    confidence:         str,
    flags:              list,
    analytics_snapshot: dict,
    latency_ms:         int,
    model_used:         str,
    retrieval_score:    float | None,
) -> int | None:
    try:
        from ..models import IntelligenceAuditLog
        log = IntelligenceAuditLog.objects.create(
            user               = user,
            session            = None,
            question           = question[:2000],
            answer             = answer[:8000],
            chunk_ids          = [c.get("chunk_id", "") for c in chunks],
            source_labels      = list({c.get("source", "") for c in chunks}),
            confidence         = confidence,
            reasoning_flags    = [f.to_dict() for f in flags],
            analytics_snapshot = analytics_snapshot,
            latency_ms         = latency_ms,
            model_used         = model_used,
            retrieval_score    = retrieval_score,
        )
        return log.pk
    except Exception as exc:
        logger.error("[intelligence] audit log failed: %s", exc)
        return None


# ── Intent-aware prompt builders ───────────────────────────────────────────────

def _build_system_prompt(
    intent:           str,
    portfolio_prompt: str,
    chunk_text:       str,
    flag_summary:     str,
    memory_block:     str,
) -> str:
    from .intent import (
        PORTFOLIO_PERFORMANCE, CONCENTRATION_RISK, FINANCE_THEORY,
        MACRO_IMPACT, REBALANCING_ALLOCATION, DIVERSIFICATION_STRATEGY,
        BEHAVIOURAL,
    )

    base_rules = """
RULES:
- Ground every claim in the data provided. Never fabricate numbers or tickers.
- Be specific: reference actual tickers, percentages, dollar values from the data.
- Distinguish fact (from portfolio data) from interpretation (your analysis).
- If evidence is weak or retrieval is empty, say so honestly.
- Write as a human analyst — natural prose, not rigid section templates.
- Keep the response under 450 words unless genuine depth is required.
- Do NOT add generic disclaimers or "consult a financial advisor" boilerplate.
- Do NOT fabricate sources. Only cite what appears in RETRIEVED KNOWLEDGE.
"""

    if intent == PORTFOLIO_PERFORMANCE:
        role = (
            "You are reviewing a client's portfolio performance. "
            "Lead with the key numbers: total value, P&L, top gainers and losers. "
            "Give a one-paragraph interpretation of what the data shows. "
            "Be direct and specific about which positions are driving performance."
        )
        context_note = "Portfolio data is your primary source. Use it specifically."

    elif intent == CONCENTRATION_RISK:
        role = (
            "You are a risk analyst assessing portfolio concentration. "
            "Open with the HHI score and top-weight percentage — explain what those numbers mean. "
            "Name the specific holdings creating concentration risk. "
            "Reference diversification principles from retrieved knowledge if available."
        )
        context_note = "Lead with risk metrics; support with retrieved theory."

    elif intent == DIVERSIFICATION_STRATEGY:
        role = (
            "You are an asset allocation strategist explaining diversification. "
            "Explain the principle clearly, then assess how well this portfolio applies it. "
            "Reference asset class correlation and sector spread. "
            "Use retrieved academic sources to back your reasoning."
        )
        context_note = "Retrieved knowledge leads; portfolio is the applied case."

    elif intent == FINANCE_THEORY:
        role = (
            "You are an investment strategist explaining a financial concept. "
            "Start with the theory clearly, then connect it directly to this portfolio. "
            "Show how the concept is visible — or violated — in the actual holdings. "
            "Cite retrieved sources naturally and specifically."
        )
        context_note = "Retrieved knowledge leads; portfolio as the application context."

    elif intent == MACRO_IMPACT:
        role = (
            "You are a macro-aware portfolio analyst. "
            "Address the macroeconomic mechanism first — what the trend means in general. "
            "Then identify which specific sectors and holdings in this portfolio "
            "are most exposed or insulated, and why. Be concrete about the transmission channel."
        )
        context_note = "Use macro principles from retrieved sources; apply to specific holdings."

    elif intent == BEHAVIOURAL:
        role = (
            "You are a behavioural finance advisor. "
            "Address the investor psychology at play — name the specific bias or behaviour pattern. "
            "Connect it to what is actually happening in this portfolio. "
            "Give grounded, evidence-based perspective on whether the concern is rational."
        )
        context_note = "Use behavioural finance from retrieved sources; anchor in portfolio reality."

    elif intent == REBALANCING_ALLOCATION:
        role = (
            "You are a portfolio construction advisor. "
            "Lead with what is currently out of balance: cash ratio, sector concentration, "
            "or position sizing. Give concrete directional guidance — trim X, add Y — "
            "with reference to target weight principles from the knowledge base."
        )
        context_note = "Lead with allocation analysis; support with theory on target weights."

    else:  # MIXED, UNSUPPORTED, fallback
        role = (
            "You are a portfolio intelligence analyst. "
            "Answer the question directly using the portfolio data and retrieved knowledge. "
            "Be specific, analytical, and honest about what the data supports versus "
            "what requires assumptions."
        )
        context_note = "Balance portfolio data and retrieved knowledge as appropriate."

    has_chunks = chunk_text and chunk_text != "No relevant sources retrieved."

    prompt = f"""You are a professional portfolio intelligence analyst.

{role}

{memory_block}PORTFOLIO DATA:
{portfolio_prompt}

RETRIEVED FINANCIAL KNOWLEDGE:
{chunk_text if has_chunks else "(No relevant sources retrieved for this question — rely on portfolio data and reasoning flags.)"}

DETECTED RISK FLAGS:
{flag_summary if flag_summary else "None detected."}

{context_note}
{base_rules}"""

    return prompt


def _build_chunk_text(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant sources retrieved."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        score = chunk.get("score", 0.0)
        parts.append(
            f"[{i}] {chunk['source']} (relevance {score:.2f})\n{chunk['text'][:250]}"
        )
    return "\n\n".join(parts)


def _build_flag_summary(flags: list) -> str:
    if not flags:
        return ""
    return "\n".join(
        f"• [{f.severity.upper()}] {f.title}: {f.explanation} → {f.recommendation}"
        for f in flags
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_portfolio_intelligence(
    user,
    question:         str,
    conversation_id:  str | None = None,
) -> IntelligenceResult:
    """
    Full portfolio intelligence pipeline.

    Returns IntelligenceResult with error=MODEL_UNAVAILABLE_ERROR if Ollama
    is not running. Never raises — all exceptions are caught and logged.
    """
    start_time = time.monotonic()
    question   = question.strip()[:MAX_QUESTION_LEN]
    logger.info("[intelligence] START user=%s q_len=%d", user.id, len(question))

    # ── Step 0: Ollama health check ────────────────────────────────────────────
    from .ollama_client import is_ollama_available
    if not is_ollama_available():
        logger.warning("[intelligence] Ollama unavailable — returning error")
        return IntelligenceResult(
            answer              = "",
            sources             = [],
            confidence          = "low",
            reasoning_flags     = [],
            portfolio_snapshot  = {},
            conversation_id     = conversation_id or "",
            conversation_title  = "",
            model_used          = "",
            retrieval_used      = False,
            intent              = "",
            memory_summary_used = False,
            error               = MODEL_UNAVAILABLE_ERROR,
        )

    # ── Step 1: Portfolio analytics ────────────────────────────────────────────
    try:
        from .analytics import build_portfolio_context
        ctx = build_portfolio_context(user)
    except Exception as exc:
        logger.error("[intelligence] analytics failed: %s", exc)
        from .analytics import PortfolioContext
        ctx = PortfolioContext(
            total_equity_value=0, total_with_cash=0, cash_balance=0, cash_ratio=1.0
        )

    has_portfolio      = len(ctx.positions) > 0
    analytics_snapshot = ctx.to_dict()
    portfolio_prompt   = ctx.to_intel_prompt()
    tickers            = [p.ticker for p in ctx.positions]

    # ── Step 2: Intent classification ──────────────────────────────────────────
    from .intent import classify_question_intent, top_k_for_intent, UNSUPPORTED
    intent = classify_question_intent(question, has_portfolio)
    top_k  = top_k_for_intent(intent)
    logger.info("[intelligence] intent=%s top_k=%d", intent, top_k)

    # ── Step 3: FAISS retrieval ────────────────────────────────────────────────
    chunks: list[dict]         = []
    retrieval_scores: list[float] = []

    if top_k > 0:
        try:
            from .vector_store import get_vector_store
            vs = get_vector_store()
            if vs.is_ready():
                chunks           = vs.retrieve(question, top_k=top_k)
                retrieval_scores = [c.get("score", 0.0) for c in chunks]
                logger.info(
                    "[intelligence] retrieved %d chunks top=%.3f",
                    len(chunks), max(retrieval_scores, default=0.0),
                )
        except Exception as exc:
            logger.error("[intelligence] retrieval error: %s", exc)

    retrieval_used = len(chunks) > 0
    top_score      = max(retrieval_scores, default=None)

    # Warn if retrieval is weak for theory/macro intents
    weak_retrieval = retrieval_used and max(retrieval_scores, default=0.0) < 0.25

    # ── Step 4: Deterministic reasoning ───────────────────────────────────────
    try:
        from .reasoning import run_reasoning
        flags = run_reasoning(ctx)
    except Exception as exc:
        logger.error("[intelligence] reasoning failed: %s", exc)
        flags = []
    logger.info("[intelligence] %d reasoning flags", len(flags))

    # ── Step 5: Load / create Conversation ────────────────────────────────────
    conversation = _get_or_create_conversation(user, conversation_id)
    is_first_turn = conversation.messages.count() == 0

    # ── Step 6: Conversation memory ────────────────────────────────────────────
    history      = _load_history(conversation)
    memory_block = _memory_prompt_block(conversation)
    memory_summary_used = bool(conversation.memory_summary)

    # ── Step 7: Confidence ─────────────────────────────────────────────────────
    confidence = compute_confidence(has_portfolio, retrieval_scores, intent)

    # Downgrade confidence if retrieval is weak for knowledge-heavy intents
    if weak_retrieval and confidence == "high":
        confidence = "medium"

    # ── Step 8: Build intent-specific prompt ───────────────────────────────────
    chunk_text    = _build_chunk_text(chunks)
    flag_summary  = _build_flag_summary(flags)
    system_prompt = _build_system_prompt(
        intent, portfolio_prompt, chunk_text, flag_summary, memory_block
    )

    # Full conversation history for multi-turn context
    ollama_history = list(history)
    ollama_history.append({"role": "user", "content": question})

    # ── Step 9: Ollama generation ──────────────────────────────────────────────
    from .ollama_client import (
        generate_with_history,
        ERROR_TIMEOUT,
        ERROR_UNAVAILABLE,
        ERROR_GENERATION_ERROR,
    )
    raw, error_code = generate_with_history(
        history     = ollama_history,
        system      = system_prompt,
        model       = OLLAMA_MODEL,
        temperature = 0.15,
        max_tokens  = 400,
    )

    if error_code is not None or not raw:
        # Map typed error codes to structured result errors
        if error_code == ERROR_TIMEOUT:
            result_error = MODEL_TIMEOUT_ERROR
            logger.warning("[intelligence] Ollama timed out")
        elif error_code == ERROR_UNAVAILABLE:
            result_error = MODEL_UNAVAILABLE_ERROR
            logger.warning("[intelligence] Ollama unavailable (post-health-check)")
        else:
            result_error = GENERATION_ERROR
            logger.error("[intelligence] Ollama generation error: %s", error_code)

        return IntelligenceResult(
            answer              = "",
            sources             = [],
            confidence          = "low",
            reasoning_flags     = [f.to_dict() for f in flags],
            portfolio_snapshot  = analytics_snapshot,
            conversation_id     = str(conversation.id),
            conversation_title  = conversation.title,
            model_used          = "",
            retrieval_used      = retrieval_used,
            intent              = intent,
            memory_summary_used = memory_summary_used,
            error               = result_error,
        )

    answer     = raw
    model_used = OLLAMA_MODEL
    logger.info("[intelligence] Ollama OK len=%d", len(answer))

    # ── Step 10: Persist + audit ───────────────────────────────────────────────
    # Build sources list
    from .source_registry import get_source
    sources: list[dict] = []
    seen_keys: set[str] = set()
    for chunk in chunks:
        key = chunk.get("source", "")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        src = get_source(key)
        if src:
            sources.append({
                "citation_label": src.citation_label,
                "title":          src.title,
                "author":         src.author,
                "institution":    src.institution,
                "year":           src.year,
                "trust_tier":     src.trust_tier,
            })

    try:
        _persist_turn(
            conversation   = conversation,
            question       = question,
            answer         = answer,
            confidence     = confidence,
            intent         = intent,
            model_used     = model_used,
            retrieval_used = retrieval_used,
            flags          = flags,
            sources        = sources,
        )
    except Exception as exc:
        logger.error("[intelligence] persist failed: %s", exc)

    # Auto-title on first turn
    if is_first_turn:
        conversation.title = _auto_title(question)
        conversation.save(update_fields=["title"])

    # Update rolling memory summary
    try:
        _update_memory_summary(conversation, question, answer, intent, flags, tickers)
    except Exception as exc:
        logger.error("[intelligence] memory update failed: %s", exc)

    latency_ms = int((time.monotonic() - start_time) * 1000)
    audit_id   = _write_audit_log(
        user               = user,
        question           = question,
        answer             = answer,
        chunks             = chunks,
        confidence         = confidence,
        flags              = flags,
        analytics_snapshot = analytics_snapshot,
        latency_ms         = latency_ms,
        model_used         = model_used,
        retrieval_score    = top_score,
    )

    logger.info(
        "[intelligence] DONE latency=%dms intent=%s conf=%s model=%s",
        latency_ms, intent, confidence, model_used,
    )

    return IntelligenceResult(
        answer              = answer,
        sources             = sources,
        confidence          = confidence,
        reasoning_flags     = [f.to_dict() for f in flags],
        portfolio_snapshot  = analytics_snapshot,
        conversation_id     = str(conversation.id),
        conversation_title  = conversation.title,
        model_used          = model_used,
        retrieval_used      = retrieval_used,
        intent              = intent,
        memory_summary_used = memory_summary_used,
        error               = None,
        audit_id            = audit_id,
    )
