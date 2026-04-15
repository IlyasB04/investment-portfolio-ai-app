"""
Groq API client — portfolio intelligence provider layer.

Groq uses an OpenAI-compatible chat completions interface.
The system prompt is the first message in the messages list (role: "system").

Interface
---------
  generate_with_history(history, system, model, temperature, max_tokens)
  is_api_configured()
  _get_model()

  All three match the signature used by intelligence.py so the swap is
  a one-line import change — no logic changes required upstream.

Error codes
-----------
  None              — success
  API_AUTH_ERROR    — missing or invalid API key
  API_RATE_LIMIT    — 429 from Groq
  TIMEOUT           — request timed out
  UNAVAILABLE       — connection-level failure
  GENERATION_ERROR  — HTTP error, bad request, or malformed response

Token budget
------------
  Default model : llama-3.3-70b-versatile  — free tier, fast, high quality
  max_tokens    : 400                       — output cap
  history depth : 4 turns (8 messages)     — set in intelligence.py MEMORY_TURNS
  chunk text    : 250 chars each           — set in intelligence.py _build_chunk_text
  temperature   : 0.15
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default model ──────────────────────────────────────────────────────────────
# llama-3.3-70b-versatile: free tier, ~400 tokens/s, strong instruction following
_DEFAULT_MODEL = "llama-3.3-70b-versatile"

# ── Typed error codes ──────────────────────────────────────────────────────────

ERROR_AUTH_ERROR       = "API_AUTH_ERROR"
ERROR_RATE_LIMIT       = "API_RATE_LIMIT"
ERROR_TIMEOUT          = "TIMEOUT"
ERROR_UNAVAILABLE      = "UNAVAILABLE"
ERROR_GENERATION_ERROR = "GENERATION_ERROR"


# ── Configuration helpers ──────────────────────────────────────────────────────

def _get_api_key() -> str | None:
    """Read GROQ_API_KEY from Django settings, falling back to env directly."""
    try:
        from django.conf import settings as _s
        key = getattr(_s, "GROQ_API_KEY", None)
        if key:
            return key
    except Exception:
        pass
    return os.getenv("GROQ_API_KEY")


def _get_model() -> str:
    """Return the configured Groq model name."""
    try:
        from django.conf import settings as _s
        return getattr(_s, "GROQ_MODEL", _DEFAULT_MODEL) or _DEFAULT_MODEL
    except Exception:
        return os.getenv("GROQ_MODEL", _DEFAULT_MODEL)


# ── Availability check (no network call) ──────────────────────────────────────

def is_api_configured() -> bool:
    """
    Returns True if GROQ_API_KEY is present in configuration.
    No network call — key presence is the only meaningful pre-flight check.
    """
    key = _get_api_key()
    return bool(key and key.strip())


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_with_history(
    history:     list[dict],
    system:      str = "",
    model:       Optional[str] = None,
    temperature: float = 0.15,
    max_tokens:  int = 400,
) -> tuple[Optional[str], Optional[str]]:
    """
    Multi-turn generation via Groq chat completions API.

    history — list of {role, content} dicts (user/assistant turns only).
              The system prompt is prepended here as role: "system".

    Returns (content, error_code).
    error_code is None on success, else one of the ERROR_* constants.
    """
    import groq

    resolved_model = model or _get_model()
    api_key        = _get_api_key()

    if not api_key:
        logger.error("[groq] GROQ_API_KEY not configured")
        return None, ERROR_AUTH_ERROR

    # Build full message list: system (optional) + user/assistant history
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history)

    logger.debug(
        "[groq] request model=%s messages=%d system_len=%d max_tokens=%d",
        resolved_model, len(messages), len(system), max_tokens,
    )

    try:
        client   = groq.Groq(api_key=api_key)
        response = client.chat.completions.create(
            model       = resolved_model,
            messages    = messages,
            temperature = temperature,
            max_tokens  = max_tokens,
        )

        # ── Extract response text defensively ─────────────────────────────────
        if not response.choices:
            logger.error(
                "[groq] empty choices — finish_reason=%s usage=%s",
                None, response.usage,
            )
            return None, ERROR_GENERATION_ERROR

        choice  = response.choices[0]
        content = (choice.message.content or "").strip()

        if not content:
            logger.error(
                "[groq] empty message content — finish_reason=%s",
                choice.finish_reason,
            )
            return None, ERROR_GENERATION_ERROR

        logger.info(
            "[groq] OK model=%s finish=%s prompt_tokens=%d completion_tokens=%d",
            resolved_model,
            choice.finish_reason,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return content, None

    except groq.AuthenticationError as exc:
        logger.error(
            "[groq] AUTHENTICATION FAILED — check GROQ_API_KEY. status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_AUTH_ERROR

    except groq.PermissionDeniedError as exc:
        logger.error(
            "[groq] PERMISSION DENIED — key may lack access to model=%s. status=%d body=%s",
            resolved_model, exc.status_code, exc.body,
        )
        return None, ERROR_AUTH_ERROR

    except groq.RateLimitError as exc:
        logger.warning(
            "[groq] RATE LIMITED — status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_RATE_LIMIT

    except groq.BadRequestError as exc:
        logger.error(
            "[groq] BAD REQUEST (400) — model=%s messages=%d status=%d message=%s body=%s",
            resolved_model, len(messages), exc.status_code, exc.message, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except groq.UnprocessableEntityError as exc:
        logger.error(
            "[groq] UNPROCESSABLE (422) — model=%s status=%d body=%s",
            resolved_model, exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except groq.NotFoundError as exc:
        logger.error(
            "[groq] NOT FOUND (404) — model=%s may be invalid. status=%d body=%s",
            resolved_model, exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except groq.InternalServerError as exc:
        logger.error(
            "[groq] SERVER ERROR (5xx) — status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except groq.APITimeoutError as exc:
        logger.warning("[groq] REQUEST TIMED OUT — model=%s error=%s", resolved_model, exc)
        return None, ERROR_TIMEOUT

    except groq.APIConnectionError as exc:
        logger.warning("[groq] CONNECTION ERROR — %s", exc)
        return None, ERROR_UNAVAILABLE

    except groq.APIResponseValidationError as exc:
        logger.error(
            "[groq] RESPONSE VALIDATION ERROR — status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except groq.APIStatusError as exc:
        logger.error(
            "[groq] API STATUS ERROR — status=%d message=%s body=%s",
            exc.status_code, exc.message, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except Exception as exc:
        logger.exception("[groq] UNEXPECTED ERROR — %s: %s", type(exc).__name__, exc)
        return None, ERROR_GENERATION_ERROR
