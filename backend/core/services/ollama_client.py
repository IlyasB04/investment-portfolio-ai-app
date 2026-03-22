"""
Ollama local LLM client.

Provides a thin, fault-tolerant wrapper around the Ollama HTTP API
(POST /api/chat) running on localhost:11434.

If Ollama is not available the functions degrade gracefully so the
intelligence pipeline can fall back to deterministic responses rather
than returning a 500 error.

Usage
-----
    from .ollama_client import generate, is_ollama_available

    if is_ollama_available():
        answer = generate(prompt, system=system_prompt)
    else:
        answer = None   # caller handles fallback
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

OLLAMA_BASE_URL  = "http://localhost:11434"
DEFAULT_MODEL    = "mistral"          # change to "llama3" etc. as needed
DEFAULT_TEMP     = 0.1                # low temperature for factual, grounded answers
REQUEST_TIMEOUT  = 60                 # seconds — local inference can be slow
MAX_TOKENS       = 1_024              # keep responses concise for RAG usage


# ── Health check ──────────────────────────────────────────────────────────────

def is_ollama_available() -> bool:
    """
    Return True if the Ollama server responds to a GET / health probe.

    Uses a short 3-second timeout so callers aren't blocked waiting for a
    server that isn't running.
    """
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.debug("[ollama] health check failed: %s", exc)
        return False


# ── Core generate call ────────────────────────────────────────────────────────

def generate(
    prompt:      str,
    system:      str = "",
    model:       str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMP,
    max_tokens:  int   = MAX_TOKENS,
) -> str | None:
    """
    Call POST /api/chat on the local Ollama server.

    Parameters
    ----------
    prompt      : The user message / question to answer.
    system      : Optional system prompt injected as the first message.
    model       : Ollama model tag (default: "mistral").
    temperature : Sampling temperature [0–1].
    max_tokens  : Maximum tokens in the generated response.

    Returns
    -------
    The assistant's reply string, or None if the call failed.
    The caller is responsible for handling the None case.
    """
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model":   model,
        "messages": messages,
        "stream":  False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
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
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            content: str = parsed["message"]["content"]
            logger.info(
                "[ollama] model=%s tokens≈%d chars=%d",
                model,
                parsed.get("eval_count", 0),
                len(content),
            )
            return content.strip()

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("[ollama] HTTP %d — %s", exc.code, body[:300])
        return None

    except urllib.error.URLError as exc:
        logger.warning("[ollama] connection error: %s", exc.reason)
        return None

    except (KeyError, json.JSONDecodeError) as exc:
        logger.error("[ollama] unexpected response format: %s", exc)
        return None

    except Exception as exc:
        logger.exception("[ollama] unexpected error: %s", exc)
        return None


# ── Multi-turn generate ────────────────────────────────────────────────────────

def generate_with_history(
    history:     list[dict],   # [{"role": "user"|"assistant", "content": "..."}]
    system:      str = "",
    model:       str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMP,
    max_tokens:  int   = MAX_TOKENS,
) -> str | None:
    """
    Multi-turn variant that accepts a pre-built message history.

    Prepends the system prompt if provided.
    """
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(history)

    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {
            "temperature": temperature,
            "num_predict": max_tokens,
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
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body    = resp.read().decode("utf-8")
            parsed  = json.loads(body)
            content = parsed["message"]["content"]
            logger.info(
                "[ollama] multi-turn model=%s turns=%d tokens≈%d",
                model,
                len(messages),
                parsed.get("eval_count", 0),
            )
            return content.strip()

    except Exception as exc:
        logger.error("[ollama] multi-turn call failed: %s", exc)
        return None
