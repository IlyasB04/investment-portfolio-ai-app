"""
RAG orchestration service.

generate_financial_response(user, question, session_id=None) → dict

Pipeline
--------
  1.  build_portfolio_context(user)       — structured analytics + narrative
  2.  retrieve_financial_context(q)       — FAISS top-k knowledge chunks
  3.  load_conversation_memory(session)   — last N ChatMessage pairs
  4.  construct_prompt(ctx, chunks, hist) — structured LLM prompt
  5.  call Claude API                     — generate response
  6.  persist_messages(session, q, resp)  — ChatMessage DB writes
  7.  return {answer, sources, session_id, context_tokens, retrieval_used}

Fallback logic
--------------
  If the vector store is not ready (index not yet ingested) or no chunks
  pass the confidence threshold, the assistant still responds using the
  portfolio analytics context alone — it just won't reference the
  knowledge base.  This ensures the endpoint is always functional even
  before `ingest_knowledge` has been run.

Prompt design
-------------
  The system prompt instructs Claude to act as a senior investment analyst,
  reference financial theory where retrieved, stay grounded in portfolio data,
  and avoid specific investment advice or return guarantees.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

MEMORY_TURNS = 5          # last N user+assistant pairs loaded from DB
MAX_QUESTION_LEN = 2_000  # hard cap on question length before truncation
MAX_CONTEXT_TOKENS = 6_000  # rough word budget for total prompt context


# ── System prompt template ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a senior investment analyst assistant embedded in a paper trading portfolio platform.
Your role is to help the user understand their portfolio with clear, strategic, and educational insight.

BEHAVIOUR RULES
---------------
1. Ground every answer in the portfolio data provided — never fabricate numbers.
2. Reference relevant financial theory and concepts when retrieved context is available.
3. Be concise and precise. Use bullet points for multi-part answers.
4. Do NOT promise returns, predict markets, or give personalised investment advice.
5. Frame all insights as educational: explain the "why" behind observations.
6. If a question cannot be answered from the available data, say so honestly.
7. For risk observations, cite the relevant metric (HHI, beta, volatility, concentration %).

CURRENT PORTFOLIO DATA
----------------------
{portfolio_context}

RELEVANT FINANCIAL KNOWLEDGE
-----------------------------
{knowledge_context}
"""

_NO_KNOWLEDGE_NOTE = (
    "[Knowledge base not yet ingested — answering from portfolio analytics only. "
    "Run `python manage.py ingest_knowledge` to enable full RAG responses.]"
)


# ── Conversation memory ────────────────────────────────────────────────────────

def _get_or_create_session(user, session_id: Optional[int]) -> "ChatSession":  # type: ignore[name-defined]
    from ..models import ChatSession
    if session_id:
        try:
            session = ChatSession.objects.get(pk=session_id, user=user)
            session.save(update_fields=["updated_at"])  # bump updated_at
            return session
        except ChatSession.DoesNotExist:
            pass
    session = ChatSession.objects.create(user=user)
    logger.debug("[rag] Created new ChatSession id=%d user=%s", session.pk, user.id)
    return session


def _load_history(session) -> list[dict]:
    """
    Return the last MEMORY_TURNS user+assistant message pairs as a list of
    {"role": "user"|"assistant", "content": "..."} dicts, oldest first.
    """
    from ..models import ChatMessage
    messages = list(
        session.messages
        .order_by("-created_at")[: MEMORY_TURNS * 2]  # over-fetch; trim below
    )
    messages.reverse()  # oldest first
    return [{"role": m.role, "content": m.content} for m in messages]


def _persist_messages(session, question: str, answer: str) -> None:
    from ..models import ChatMessage
    ChatMessage.objects.create(session=session, role=ChatMessage.Role.USER, content=question)
    ChatMessage.objects.create(session=session, role=ChatMessage.Role.ASSISTANT, content=answer)
    logger.debug("[rag] Persisted turn to session=%d", session.pk)


# ── Prompt construction ────────────────────────────────────────────────────────

def _format_knowledge_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a readable block for the system prompt."""
    if not chunks:
        return _NO_KNOWLEDGE_NOTE

    parts = []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(
            f"[{i}] Source: {chunk['source']} (relevance: {chunk['score']:.2f})\n"
            f"{chunk['text']}"
        )
    return "\n\n".join(parts)


def _format_history_messages(history: list[dict]) -> list[dict]:
    """Return history as a list of {"role": ..., "content": ...} Claude messages."""
    return history  # already in the right format


# ── Claude API call ────────────────────────────────────────────────────────────

def _call_claude(
    *,
    system: str,
    history: list[dict],
    question: str,
) -> tuple[str, int]:
    """
    Call Claude with the constructed prompt.
    Returns (answer_text, total_input_tokens).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return (
            "The AI assistant is not configured. "
            "Please set ANTHROPIC_API_KEY in the backend .env file.",
            0,
        )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        messages = [*history, {"role": "user", "content": question}]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1_500,
            system=system,
            messages=messages,
        )

        answer = response.content[0].text
        input_tokens = response.usage.input_tokens if response.usage else 0

        logger.info(
            "[rag] Claude call complete: input_tokens=%d output_tokens=%d",
            input_tokens,
            response.usage.output_tokens if response.usage else 0,
        )
        return answer, input_tokens

    except Exception as exc:
        logger.error("[rag] Claude API error: %s", exc)
        return f"AI assistant error: {exc}", 0


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_financial_response(
    user,
    question: str,
    session_id: Optional[int] = None,
) -> dict:
    """
    Full RAG pipeline.  Always returns a dict — never raises.

    Return schema
    -------------
    {
      "answer":          str,
      "sources":         [{"source": str, "score": float, "chunk_id": int}],
      "session_id":      int,
      "retrieval_used":  bool,
      "context_tokens":  int,   # approximate input tokens sent to Claude
    }
    """
    # Truncate absurdly long questions
    if len(question) > MAX_QUESTION_LEN:
        question = question[:MAX_QUESTION_LEN] + "…"

    # ── Step 1: Portfolio analytics context ───────────────────────────────────
    try:
        from .analytics import build_portfolio_context
        portfolio_ctx = build_portfolio_context(user)
        portfolio_narrative = portfolio_ctx.narrative
        logger.info(
            "[rag] Portfolio context: equity=$%.2f positions=%d HHI=%.3f",
            portfolio_ctx.total_equity_value,
            len(portfolio_ctx.positions),
            portfolio_ctx.hhi,
        )
    except Exception as exc:
        logger.error("[rag] Portfolio context error: %s", exc)
        portfolio_narrative = "[Portfolio data unavailable — analytics service error]"

    # ── Step 2: Retrieve relevant knowledge ───────────────────────────────────
    retrieved_chunks: list[dict] = []
    retrieval_used = False

    try:
        from .vector_store import get_vector_store
        store = get_vector_store()

        if store.is_ready():
            retrieved_chunks = store.retrieve(question, top_k=4)
            retrieval_used = bool(retrieved_chunks)
            logger.info(
                "[rag] Retrieval: %d chunks above threshold.  Sources: %s",
                len(retrieved_chunks),
                list({c["source"] for c in retrieved_chunks}),
            )
        else:
            logger.info("[rag] Vector store not ready — skipping retrieval (fallback mode)")
    except Exception as exc:
        logger.warning("[rag] Retrieval error (non-fatal): %s", exc)

    # ── Step 3: Conversation memory ───────────────────────────────────────────
    try:
        session = _get_or_create_session(user, session_id)
        history = _load_history(session)
        logger.debug("[rag] Loaded %d history messages for session=%d", len(history), session.pk)
    except Exception as exc:
        logger.error("[rag] Session/history error: %s", exc)
        # Create a throwaway session so we can still respond
        from ..models import ChatSession
        session = ChatSession.objects.create(user=user)
        history = []

    # ── Step 4: Construct system prompt ───────────────────────────────────────
    knowledge_block = _format_knowledge_context(retrieved_chunks)

    # Rough token estimation: 1 token ≈ 0.75 words
    approx_tokens = int(
        (len(portfolio_narrative.split()) + len(knowledge_block.split())) / 0.75
    )
    logger.info(
        "[rag] Prompt budget — portfolio_words=%d knowledge_words=%d ~tokens=%d",
        len(portfolio_narrative.split()),
        len(knowledge_block.split()),
        approx_tokens,
    )

    system = _SYSTEM_PROMPT.format(
        portfolio_context=portfolio_narrative,
        knowledge_context=knowledge_block,
    )

    # ── Step 5: Call Claude ───────────────────────────────────────────────────
    answer, input_tokens = _call_claude(
        system=system,
        history=history,
        question=question,
    )

    # ── Step 6: Persist messages ──────────────────────────────────────────────
    try:
        _persist_messages(session, question, answer)
    except Exception as exc:
        logger.error("[rag] Failed to persist messages: %s", exc)

    # ── Step 7: Build response ────────────────────────────────────────────────
    sources = [
        {"source": c["source"], "score": c["score"], "chunk_id": c["chunk_id"]}
        for c in retrieved_chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
        "session_id": session.pk,
        "retrieval_used": retrieval_used,
        "context_tokens": input_tokens or approx_tokens,
    }
