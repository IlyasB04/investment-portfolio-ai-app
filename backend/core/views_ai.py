"""
AI Portfolio Intelligence views.

Endpoints
---------
  GET  /api/ai/health/                          — API key status + RAG index readiness
  POST /api/ai/conversations/                   — create a new named conversation
  GET  /api/ai/conversations/                   — list all conversations for the user
  GET  /api/ai/conversations/<uuid>/messages/   — load full message history
  DELETE /api/ai/conversations/<uuid>/          — delete a conversation
  POST /api/ai/intelligence/                    — portfolio intelligence (requires Groq API key)
"""

import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)


# ── Health endpoint ────────────────────────────────────────────────────────────

@api_view(["GET"])
def ai_health(request):
    """
    GET /api/ai/health/

    Checks API key configuration and RAG index readiness.
    No network call is made — key presence is the availability signal.

    Response
    --------
    {
      "api_available":   bool,
      "rag_index_ready": bool,
      "model":           str,
      "status":          "ready" | "api_not_configured"
    }
    """
    from .services.groq_client import is_api_configured, _get_model

    api_up    = is_api_configured()
    rag_ready = False
    try:
        from .services.vector_store import get_vector_store
        rag_ready = get_vector_store().is_ready()
    except Exception:
        pass

    return JsonResponse({
        "api_available":   api_up,
        "rag_index_ready": rag_ready,
        "model":           _get_model(),
        "status":          "ready" if api_up else "api_not_configured",
    })


# ── Conversation CRUD ──────────────────────────────────────────────────────────

@api_view(["POST"])
def create_conversation(request):
    """
    POST /api/ai/conversations/

    Body (optional): { "title": "string" }

    Creates a new empty conversation for the authenticated user.

    Response
    --------
    {
      "id":           str (UUID),
      "title":        str,
      "created_at":   ISO-8601,
      "updated_at":   ISO-8601,
      "message_count": 0
    }
    """
    from .models import Conversation

    title = (request.data.get("title") or "New Conversation")[:200]
    conv  = Conversation.objects.create(user=request.user, title=title)

    return JsonResponse({
        "id":            str(conv.id),
        "title":         conv.title,
        "created_at":    conv.created_at.isoformat(),
        "updated_at":    conv.updated_at.isoformat(),
        "message_count": 0,
    }, status=201)


@api_view(["GET"])
def list_conversations(request):
    """
    GET /api/ai/conversations/

    Returns conversations ordered by most recently updated first (max 50).

    Response
    --------
    {
      "conversations": [
        {
          "id":            str (UUID),
          "title":         str,
          "last_question": str,
          "created_at":    ISO-8601,
          "updated_at":    ISO-8601,
          "message_count": int
        }, ...
      ]
    }
    """
    from .models import Conversation
    from django.db.models import Count

    convs = (
        Conversation.objects
        .filter(user=request.user)
        .annotate(message_count=Count("messages"))
        .order_by("-updated_at")[:50]
    )

    return JsonResponse({
        "conversations": [
            {
                "id":            str(c.id),
                "title":         c.title,
                "last_question": c.last_question[:120] if c.last_question else "",
                "created_at":    c.created_at.isoformat(),
                "updated_at":    c.updated_at.isoformat(),
                "message_count": c.message_count,
            }
            for c in convs
        ]
    })


@api_view(["GET", "DELETE"])
def conversation_detail(request, conversation_id: str):
    """
    GET    /api/ai/conversations/<uuid>/messages/  — load messages
    DELETE /api/ai/conversations/<uuid>/           — delete conversation

    GET response
    ------------
    {
      "id":       str,
      "title":    str,
      "messages": [ { id, role, content, timestamp, confidence, intent,
                      model_used, retrieval_used, sources, reasoning_flags } ]
    }
    """
    from .models import Conversation

    try:
        conv = Conversation.objects.get(pk=conversation_id, user=request.user)
    except (Conversation.DoesNotExist, ValueError):
        return JsonResponse({"error": "Conversation not found."}, status=404)

    if request.method == "DELETE":
        conv.delete()
        return JsonResponse({"deleted": True})

    # GET — load messages
    try:
        limit = min(int(request.GET.get("limit", 200)), 400)
    except ValueError:
        limit = 200

    messages = list(conv.messages.order_by("created_at")[:limit])

    return JsonResponse({
        "id":    str(conv.id),
        "title": conv.title,
        "messages": [
            {
                "id":              str(m.id),
                "role":            m.role,
                "content":         m.content,
                "timestamp":       m.created_at.isoformat(),
                "confidence":      m.confidence or None,
                "intent":          m.intent or None,
                "model_used":      m.model_used or None,
                "retrieval_used":  m.retrieval_used,
                "sources":         m.sources_json,
                "reasoning_flags": m.reasoning_flags_json,
            }
            for m in messages
        ],
    })


# ── Portfolio Intelligence endpoint ───────────────────────────────────────────

@api_view(["POST"])
def intelligence_chat(request):
    """
    POST /api/ai/intelligence/

    Requires GROQ_API_KEY to be configured. Returns an error response if the
    key is missing, rate-limited, or the model fails to respond.

    Request body
    ------------
    {
      "message":         str,           required
      "conversation_id": str | null     UUID of existing conversation, or null to create new
    }

    Response (200)
    --------------
    {
      "answer":               str,
      "sources":              list[dict],
      "confidence":           "high" | "medium" | "low",
      "reasoning_flags":      list[dict],
      "portfolio_snapshot":   dict,
      "conversation_id":      str (UUID),
      "conversation_title":   str,
      "model_used":           str,
      "retrieval_used":       bool,
      "intent":               str,
      "memory_summary_used":  bool,
      "audit_id":             int | null
    }

    Error responses
    ---------------
    503 API_AUTH_ERROR  — GROQ_API_KEY missing or invalid
    429 API_RATE_LIMIT  — Groq rate limit reached
    504 MODEL_TIMEOUT   — model took too long to respond
    503 SERVICE_UNAVAILABLE — connection-level failure
    500 GENERATION_ERROR — model returned an unusable response
    400/500 { "error": "..." }
    """
    message = (request.data.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "message is required."}, status=400)
    if len(message) > 2_000:
        return JsonResponse({"error": "message too long (max 2000 chars)."}, status=400)

    conversation_id: str | None = request.data.get("conversation_id") or None

    logger.info(
        "[intelligence_chat] user=%s conv_id=%s q_len=%d",
        request.user.id, conversation_id, len(message),
    )

    try:
        from .services.intelligence import (
            generate_portfolio_intelligence,
            MODEL_UNAVAILABLE_ERROR,
            MODEL_TIMEOUT_ERROR,
            GENERATION_ERROR,
            API_AUTH_ERROR,
            API_RATE_LIMIT_ERROR,
        )
        result = generate_portfolio_intelligence(
            user            = request.user,
            question        = message,
            conversation_id = conversation_id,
        )

        if result.error == API_AUTH_ERROR:
            return JsonResponse({
                "error":   "API_AUTH_ERROR",
                "message": "Assistant API key is not configured. Contact your administrator.",
            }, status=503)

        if result.error == API_RATE_LIMIT_ERROR:
            return JsonResponse({
                "error":   "API_RATE_LIMIT",
                "message": "Rate limit reached. Please wait a moment and try again.",
            }, status=429)

        if result.error == MODEL_TIMEOUT_ERROR:
            return JsonResponse({
                "error":   "MODEL_TIMEOUT",
                "message": "The assistant took too long to respond. Try a shorter question.",
            }, status=504)

        if result.error == MODEL_UNAVAILABLE_ERROR:
            return JsonResponse({
                "error":   "SERVICE_UNAVAILABLE",
                "message": "The assistant service is temporarily unavailable. Please try again.",
            }, status=503)

        if result.error == GENERATION_ERROR:
            return JsonResponse({
                "error":   "GENERATION_ERROR",
                "message": "The assistant encountered an error. Please try again.",
            }, status=500)

        return JsonResponse({
            "answer":              result.answer,
            "sources":             result.sources,
            "confidence":          result.confidence,
            "reasoning_flags":     result.reasoning_flags,
            "portfolio_snapshot":  result.portfolio_snapshot,
            "conversation_id":     result.conversation_id,
            "conversation_title":  result.conversation_title,
            "model_used":          result.model_used,
            "retrieval_used":      result.retrieval_used,
            "intent":              result.intent,
            "memory_summary_used": result.memory_summary_used,
            "audit_id":            result.audit_id,
        })

    except Exception as exc:
        logger.exception("[intelligence_chat] Unhandled error: %s", exc)
        return JsonResponse({"error": f"Intelligence service error: {exc}"}, status=500)


# ── Legacy endpoints (kept for backward compatibility) ────────────────────────

@api_view(["GET"])
def ai_history(request):
    """
    GET /api/ai/history/?session_id=X  — legacy single-session history endpoint.
    Kept for any existing integrations. Prefer /api/ai/conversations/<uuid>/messages/.
    """
    from .models import ChatSession

    raw_session_id = request.GET.get("session_id", "").strip()
    if not raw_session_id:
        return JsonResponse({"session_id": None, "messages": []})

    try:
        session_id = int(raw_session_id)
    except ValueError:
        return JsonResponse({"error": "session_id must be an integer."}, status=400)

    try:
        limit = min(int(request.GET.get("limit", 60)), 120)
    except ValueError:
        limit = 60

    try:
        session = ChatSession.objects.get(pk=session_id, user=request.user)
    except ChatSession.DoesNotExist:
        return JsonResponse({"session_id": None, "messages": []})

    messages = list(session.messages.order_by("created_at")[:limit])
    return JsonResponse({
        "session_id": session.pk,
        "messages": [
            {
                "role":            m.role,
                "content":         m.content,
                "timestamp":       m.created_at.isoformat(),
                "confidence":      m.confidence or None,
                "intent":          m.intent or None,
                "model_used":      m.model_used or None,
                "retrieval_used":  m.retrieval_used,
                "reasoning_flags": m.reasoning_flags,
                "sources":         m.sources,
            }
            for m in messages
        ],
    })


@api_view(["POST"])
def portfolio_chat(request):
    """POST /api/ai/chat/ — legacy no-RAG endpoint. Kept for backward compat."""
    return JsonResponse(
        {"error": "This endpoint is deprecated. Use POST /api/ai/intelligence/ instead."},
        status=410,
    )


@api_view(["POST"])
def financial_chat(request):
    """POST /api/ai/financial-chat/ — legacy Claude RAG endpoint. Kept for backward compat."""
    return JsonResponse(
        {"error": "This endpoint is deprecated. Use POST /api/ai/intelligence/ instead."},
        status=410,
    )
