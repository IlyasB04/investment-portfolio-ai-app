"""
Anthropic Claude API client — replaces ollama_client as the model provider layer.

Design constraints
------------------
  - API key read from Django settings only (never exposed to frontend)
  - Single generate_with_history() entry point matching the existing call signature
  - Typed error codes for clean caller-side branching
  - Conservative token budget: max_tokens=400, short history, 250-char chunks
  - No health-check network call at startup — key presence is the availability signal

Error codes
-----------
  None              — success
  API_AUTH_ERROR    — missing or invalid API key (401 / misconfiguration)
  API_RATE_LIMIT    — 429 from Anthropic
  TIMEOUT           — request timed out
  UNAVAILABLE       — connection-level failure
  GENERATION_ERROR  — HTTP error or malformed response

Cost controls
-------------
  Default model : claude-haiku-4-5-20251001  — cheapest Claude model (~$0.001 / call)
  max_tokens    : 400                         — limits output spend
  history depth : 4 turns (8 messages)       — set in intelligence.py MEMORY_TURNS
  chunk text    : 250 chars each             — set in intelligence.py _build_chunk_text
  temperature   : 0.15                        — low temp = fewer re-tries needed
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default model ──────────────────────────────────────────────────────────────

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ── Typed error codes ──────────────────────────────────────────────────────────

ERROR_AUTH_ERROR       = "API_AUTH_ERROR"
ERROR_RATE_LIMIT       = "API_RATE_LIMIT"
ERROR_TIMEOUT          = "TIMEOUT"
ERROR_UNAVAILABLE      = "UNAVAILABLE"
ERROR_GENERATION_ERROR = "GENERATION_ERROR"


# ── Configuration helpers ──────────────────────────────────────────────────────

def _get_api_key() -> str | None:
    """Read ANTHROPIC_API_KEY from Django settings, falling back to env directly."""
    try:
        from django.conf import settings as _s
        key = getattr(_s, "ANTHROPIC_API_KEY", None)
        if key:
            return key
    except Exception:
        pass
    return os.getenv("ANTHROPIC_API_KEY")


def _get_model() -> str:
    """Return the configured Claude model name."""
    try:
        from django.conf import settings as _s
        return getattr(_s, "ANTHROPIC_MODEL", _DEFAULT_MODEL) or _DEFAULT_MODEL
    except Exception:
        return os.getenv("ANTHROPIC_MODEL", _DEFAULT_MODEL)


# ── Availability check (no network call) ──────────────────────────────────────

def is_api_configured() -> bool:
    """
    Returns True if ANTHROPIC_API_KEY is present in configuration.

    Intentionally fast — no network call. API key presence is the
    only meaningful pre-flight check we can do without billing usage.
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
    Multi-turn generation via Anthropic Messages API.

    history — list of {role, content} dicts in chronological order.
              Must end with a user message (standard conversation format).
    system  — system prompt passed to the model.

    Returns (content, error_code).
    error_code is None on success, else one of the ERROR_* constants.
    """
    import anthropic

    resolved_model = model or _get_model()
    api_key        = _get_api_key()

    if not api_key:
        logger.error("[anthropic] ANTHROPIC_API_KEY not configured")
        return None, ERROR_AUTH_ERROR

    try:
        client = anthropic.Anthropic(api_key=api_key)

        kwargs: dict = {
            "model":       resolved_model,
            "max_tokens":  max_tokens,
            "messages":    history,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        logger.debug(
            "[anthropic] sending request model=%s messages=%d system_len=%d max_tokens=%d",
            resolved_model, len(history), len(system), max_tokens,
        )

        response = client.messages.create(**kwargs)

        # ── Extract text content defensively ──────────────────────────────────
        if not response.content:
            logger.error(
                "[anthropic] empty content list — stop_reason=%s usage=%s",
                response.stop_reason, response.usage,
            )
            return None, ERROR_GENERATION_ERROR

        first_block = response.content[0]
        if not hasattr(first_block, "text"):
            logger.error(
                "[anthropic] first content block has no .text — type=%s block=%r",
                type(first_block).__name__, first_block,
            )
            return None, ERROR_GENERATION_ERROR

        content = first_block.text.strip()
        logger.info(
            "[anthropic] OK model=%s stop_reason=%s input_tokens=%d output_tokens=%d",
            resolved_model,
            response.stop_reason,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return content, None

    except anthropic.AuthenticationError as exc:
        logger.error(
            "[anthropic] AUTHENTICATION FAILED — check ANTHROPIC_API_KEY. status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_AUTH_ERROR

    except anthropic.PermissionDeniedError as exc:
        logger.error(
            "[anthropic] PERMISSION DENIED — key may lack access to model=%s. status=%d body=%s",
            resolved_model, exc.status_code, exc.body,
        )
        return None, ERROR_AUTH_ERROR

    except anthropic.RateLimitError as exc:
        logger.warning(
            "[anthropic] RATE LIMITED — status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_RATE_LIMIT

    except anthropic.BadRequestError as exc:
        logger.error(
            "[anthropic] BAD REQUEST (400) — invalid messages or parameters. "
            "model=%s messages=%d status=%d message=%s body=%s",
            resolved_model, len(history), exc.status_code, exc.message, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except anthropic.UnprocessableEntityError as exc:
        logger.error(
            "[anthropic] UNPROCESSABLE (422) — request rejected. "
            "model=%s status=%d message=%s body=%s",
            resolved_model, exc.status_code, exc.message, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except anthropic.NotFoundError as exc:
        logger.error(
            "[anthropic] NOT FOUND (404) — model not found or invalid. "
            "model=%s status=%d body=%s",
            resolved_model, exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except anthropic.InternalServerError as exc:
        logger.error(
            "[anthropic] ANTHROPIC SERVER ERROR (5xx) — status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except anthropic.APITimeoutError as exc:
        logger.warning("[anthropic] REQUEST TIMED OUT — model=%s error=%s", resolved_model, exc)
        return None, ERROR_TIMEOUT

    except anthropic.APIConnectionError as exc:
        logger.warning("[anthropic] CONNECTION ERROR — %s", exc)
        return None, ERROR_UNAVAILABLE

    except anthropic.APIResponseValidationError as exc:
        logger.error(
            "[anthropic] RESPONSE VALIDATION ERROR — SDK could not parse response. "
            "status=%d body=%s",
            exc.status_code, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except anthropic.APIStatusError as exc:
        # Catch-all for any remaining 4xx/5xx not handled above
        logger.error(
            "[anthropic] API STATUS ERROR — status=%d message=%s body=%s",
            exc.status_code, exc.message, exc.body,
        )
        return None, ERROR_GENERATION_ERROR

    except Exception as exc:
        logger.exception("[anthropic] UNEXPECTED ERROR — %s: %s", type(exc).__name__, exc)
        return None, ERROR_GENERATION_ERROR
