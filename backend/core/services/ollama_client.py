"""
Ollama local LLM client — stabilised for demo reliability.

Design constraints
------------------
  - Hard 25-second generation timeout  (prevents thread blocking / laptop freeze)
  - Fast 2-second health-check timeout (never delays startup)
  - num_ctx capped at 2048             (limits KV-cache RAM; Mistral fits cleanly)
  - Configurable model via OLLAMA_MODEL Django setting
  - Typed error codes returned alongside content so callers can surface
    distinct UI states (timeout ≠ offline ≠ generation failure)

Error codes
-----------
  None              — success
  TIMEOUT           — urlopen timed out during generation
  UNAVAILABLE       — connection refused / Ollama not running
  GENERATION_ERROR  — HTTP error or malformed response

Hardware note
-------------
  Reducing num_ctx and max_tokens reduces inference RAM pressure and shortens
  generation time. It does NOT eliminate the possibility of a laptop being too
  slow to respond within 25 seconds — that is a hardware limitation.
  The timeout ensures the Django thread is always released within ~26 seconds
  regardless of model speed.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Optional

try:
    from django.conf import settings as _django_settings
    _DJANGO_AVAILABLE = True
except Exception:
    _DJANGO_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

OLLAMA_BASE_URL      = "http://localhost:11434"
HEALTH_CHECK_TIMEOUT = 2     # seconds — fast probe, never delays anything
GENERATION_TIMEOUT   = 25    # seconds — hard cap to prevent blocking / freezing

# Default model — override via Django settings: OLLAMA_MODEL = "llama3.2"
# Lighter alternatives for constrained laptops: "llama3.2", "phi3", "qwen2:1.5b"
_DEFAULT_MODEL = "mistral"

MAX_TOKENS       = 420       # keeps responses focused; reduces generation time
NUM_CTX          = 2048      # context window cap — critical for RAM management
DEFAULT_TEMP     = 0.1

# ── Typed error codes ──────────────────────────────────────────────────────────

ERROR_TIMEOUT          = "TIMEOUT"
ERROR_UNAVAILABLE      = "UNAVAILABLE"
ERROR_GENERATION_ERROR = "GENERATION_ERROR"


def _get_model() -> str:
    """Return the configured model name, with fallback to default."""
    if _DJANGO_AVAILABLE:
        try:
            return getattr(_django_settings, "OLLAMA_MODEL", _DEFAULT_MODEL)
        except Exception:
            pass
    return _DEFAULT_MODEL


# ── Health check ───────────────────────────────────────────────────────────────

def is_ollama_available() -> bool:
    """
    Fast health probe — returns within 2 seconds.

    Uses GET /api/tags which is lightweight (metadata only, no model loading).
    Returns False on ANY exception so the caller never blocks.
    """
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=HEALTH_CHECK_TIMEOUT) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.debug("[ollama] health check failed: %s", exc)
        return False


# ── Internal _call helper ──────────────────────────────────────────────────────

def _call(
    messages:    list[dict],
    model:       str,
    temperature: float,
    max_tokens:  int,
) -> tuple[Optional[str], Optional[str]]:
    """
    POST /api/chat and return (content, error_code).

    content    — the assistant reply, or None on failure
    error_code — None on success, or one of the ERROR_* constants

    Always returns within GENERATION_TIMEOUT seconds.
    """
    payload = {
        "model":   model,
        "messages": messages,
        "stream":  False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx":     NUM_CTX,       # cap context window → less RAM pressure
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data    = data,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=GENERATION_TIMEOUT) as resp:
            body    = resp.read().decode("utf-8")
            parsed  = json.loads(body)
            content = parsed["message"]["content"].strip()
            logger.info(
                "[ollama] OK model=%s tokens≈%d chars=%d",
                model,
                parsed.get("eval_count", 0),
                len(content),
            )
            return content, None

    except socket.timeout:
        logger.warning("[ollama] generation timed out after %ds", GENERATION_TIMEOUT)
        return None, ERROR_TIMEOUT

    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "connection refused" in reason.lower() or "connection reset" in reason.lower():
            logger.warning("[ollama] connection refused — is Ollama running?")
            return None, ERROR_UNAVAILABLE
        logger.warning("[ollama] URL error: %s", reason)
        return None, ERROR_UNAVAILABLE

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("[ollama] HTTP %d — %s", exc.code, body[:200])
        return None, ERROR_GENERATION_ERROR

    except (KeyError, json.JSONDecodeError) as exc:
        logger.error("[ollama] bad response format: %s", exc)
        return None, ERROR_GENERATION_ERROR

    except Exception as exc:
        logger.exception("[ollama] unexpected error: %s", exc)
        return None, ERROR_GENERATION_ERROR


# ── Public API ─────────────────────────────────────────────────────────────────

def generate(
    prompt:      str,
    system:      str = "",
    model:       Optional[str] = None,
    temperature: float = DEFAULT_TEMP,
    max_tokens:  int   = MAX_TOKENS,
) -> tuple[Optional[str], Optional[str]]:
    """
    Single-turn generation.

    Returns (content, error_code).
    error_code is None on success, else one of ERROR_TIMEOUT / ERROR_UNAVAILABLE /
    ERROR_GENERATION_ERROR.
    """
    model = model or _get_model()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return _call(messages, model, temperature, max_tokens)


def generate_with_history(
    history:     list[dict],
    system:      str = "",
    model:       Optional[str] = None,
    temperature: float = DEFAULT_TEMP,
    max_tokens:  int   = MAX_TOKENS,
) -> tuple[Optional[str], Optional[str]]:
    """
    Multi-turn generation.

    history — list of {role, content} dicts in chronological order.
    Returns (content, error_code).
    """
    model = model or _get_model()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history)
    logger.info("[ollama] generate model=%s turns=%d", model, len(messages))
    return _call(messages, model, temperature, max_tokens)
