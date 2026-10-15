"""LLM client supporting the Gemini Free API with offline heuristic fallback."""

from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Transient-error retry policy (Gemini free tier: 429 rate limit, 503 capacity).
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CAP_SECONDS = 20.0

# Client-side throttle. The configured Gemini key is served by a proxy with a
# small requests-per-minute budget, so we serialise LLM calls and leave a gap
# between them instead of firing them back-to-back and burning the quota.
_MIN_INTERVAL_SECONDS = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "4.0"))
_request_lock = threading.Lock()
_last_request_at = 0.0
_last_request_failed_quota = False  # skip throttle after hard-quota failures


def _throttle() -> None:
    """Block until enough time has passed since the previous LLM request.

    Skip the wait when the previous request failed with an exhausted quota
    (hard 429) — retrying immediately will also fail, and waiting 4 s just
    wastes the user's time without improving the outcome.
    """
    global _last_request_at, _last_request_failed_quota
    if _MIN_INTERVAL_SECONDS <= 0:
        return
    if _last_request_failed_quota:
        _last_request_failed_quota = False
        _last_request_at = time.monotonic()
        return
    with _request_lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL_SECONDS - (now - _last_request_at)
        if wait > 0:
            logger.debug("Throttling LLM request for %.1fs", wait)
            time.sleep(wait)
        _last_request_at = time.monotonic()

# HTTP codes worth retrying. 429 = rate limited, 5xx = transient server/overload.
_RETRYABLE_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 529}

# Markers for a 429 that means "your quota is exhausted" rather than "slow
# down". These never clear by retrying: the counter only resets at the end of
# the billing/period window. Retrying just burns seconds before we fall back,
# so we fail fast and let the caller switch provider instead.
_HARD_QUOTA_MARKERS = (
    "exceeded your current quota",
    "quota exceeded",
    "resource_exhausted",
    "insufficient_quota",
    "billing",
    "check your plan",
    "out of credits",
    "daily limit",
    "requests per day",
)


def _is_hard_quota_error(exc: Exception) -> bool:
    """Return True when the failure is an exhausted quota, not a rate limit.

    Gemini's free tier reports a genuinely exhausted budget as HTTP 429, which
    looks identical to a momentary burst overage. Retrying a hard-quota 429 is
    guaranteed to fail four times and delay the offline fallback by ~13s.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _HARD_QUOTA_MARKERS)


def _is_transient_error(exc: Exception) -> bool:
    """Return True when the error is likely to clear if we simply wait and retry."""
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRYABLE_CODES
    # AgentError wraps the HTTP code in its message, so fall back to text matching.
    text = str(exc).lower()
    if any(f"{code}" in text for code in _RETRYABLE_CODES):
        return True
    return any(
        marker in text
        for marker in (
            "too many requests",
            "rate limit",
            "high demand",
            "unavailable",
            "overloaded",
            "temporarily",
            "timed out",
            "timeout",
            "connection reset",
            "bad gateway",
        )
    )


def _backoff_delay(exc: Exception, attempt: int) -> float:
    """Exponential backoff with jitter, honouring Retry-After when present."""
    # Respect the server's Retry-After hint if it sent one.
    cause = exc.__cause__
    headers = getattr(cause, "headers", None)
    hint = None
    if headers is not None:
        try:
            hint = headers.get("Retry-After")
        except Exception:  # noqa: BLE001 - header containers can be exotic
            hint = None
    if isinstance(hint, (int, float)) or (isinstance(hint, str) and hint.isdigit()):
        return min(float(hint), _BACKOFF_CAP_SECONDS)

    delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    # Full jitter avoids a thundering herd when several requests fail together.
    delay = random.uniform(delay * 0.5, delay)
    return min(delay, _BACKOFF_CAP_SECONDS)


def _short(exc: Exception | None) -> str:
    """Collapse a noisy SDK/urllib error into a single readable line."""
    if exc is None:
        return "unknown error"
    text = " ".join(str(exc).split())
    return text if len(text) <= 220 else text[:220] + "…"


# Fallback chain for the Gemini free tier. When a model is overloaded
# ("experiencing high demand"), a sibling Flash model usually has capacity.
# Keep the list short — every extra candidate burns another HTTPS round-trip
# on the failure path.
_GEMINI_FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-flash-latest",
    "gemini-3-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-pro-latest",
)


def _gemini_model_candidates(primary: str) -> list[str]:
    """Return the configured model plus any fallbacks, deduplicated and in order."""
    seen: set[str] = set()
    chain: list[str] = []
    for name in (primary, *_GEMINI_FALLBACK_MODELS):
        if name and name not in seen:
            chain.append(name)
            seen.add(name)
    return chain


def _parse_gemini_response(body: str) -> dict[str, Any]:
    """Decode a Gemini generateContent response into the internal shape."""
    data = json.loads(body)
    candidate = (data.get("candidates") or [{}])[0]
    content_obj = candidate.get("content") or {}
    parts = content_obj.get("parts") or []

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for idx, part in enumerate(parts):
        text = part.get("text")
        if text:
            text_parts.append(text)
        function_call = part.get("functionCall")
        if function_call:
            name = function_call.get("name") or ""
            args_raw = function_call.get("args") or {}
            tool_calls.append({
                "id": f"call_{idx}",
                "name": name,
                "arguments": json.dumps(args_raw, ensure_ascii=False),
            })

    return {"content": "\n".join(text_parts), "tool_calls": tool_calls, "raw_parts": parts}


class LLMClient:
    """Multi-provider LLM client. Falls back to local router if no provider configured."""

    def is_configured(self) -> bool:
        return self._active_provider() != "local"

    def active_provider(self) -> str:
        return self._active_provider()

    def _active_provider(self) -> str:
        explicit = settings.llm_provider.lower().strip()
        if explicit == "gemini" and settings.gemini_api_key.strip():
            return "gemini"
        if explicit == "local":
            return "local"
        # Auto-detect: prefer Gemini if a key is present, else fall back to local.
        if settings.gemini_api_key.strip():
            return "gemini"
        return "local"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        provider = self._active_provider()
        if provider == "local":
            raise AgentError("No LLM provider is configured.")

        # Retry loop with exponential backoff + jitter. Gemini free tier is
        # aggressively rate-limited (429) and prone to capacity spikes (503),
        # both of which clear on their own after a short wait.
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            _throttle()
            try:
                return self._chat_gemini(messages, tools)
            except Exception as exc:
                last_exc = exc
                # An exhausted quota will still be exhausted in 2 seconds, so
                # skip the backoff entirely and surface it to the caller now.
                if _is_hard_quota_error(exc):
                    logger.error(
                        "LLM quota exhausted (%s), not retrying: %s", provider, _short(exc)
                    )
                    # Mark so the next request skips the throttle wait.
                    import app.agent.llm_client as llm_module
                    llm_module._last_request_failed_quota = True
                    raise AgentError(f"LLM quota exhausted: {_short(exc)}") from exc
                if not _is_transient_error(exc) or attempt == _MAX_ATTEMPTS:
                    logger.error(
                        "LLM request failed (%s) after %d attempt(s): %s",
                        provider, attempt, exc,
                    )
                    raise AgentError(f"LLM request failed: {_short(exc)}") from exc
                delay = _backoff_delay(exc, attempt)
                logger.warning(
                    "Transient LLM error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, _MAX_ATTEMPTS, delay, _short(exc),
                )
                time.sleep(delay)

        raise AgentError(f"LLM request failed: {_short(last_exc)}") from last_exc

    # ── Gemini Free API (Google AI Studio) ────────────────────────────────────
    def _chat_gemini(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        import urllib.request
        import urllib.error

        # Convert OpenAI-style messages to Gemini contents format
        system_text, contents = _convert_to_gemini_contents(messages)
        # Convert tools + contents to Gemini request payload
        gemini_tools = _convert_to_gemini_tools(tools, system_text, contents)

        payload = json.dumps(gemini_tools).encode("utf-8")
        # Try the configured model first, then walk a small fallback list so a
        # single overloaded model ("experiencing high demand") does not freeze
        # the whole agent. The order is fast → cheap → smallest fallback.
        candidates = _gemini_model_candidates(settings.gemini_model)
        last_exc: Exception | None = None
        for model_name in candidates:
            url = (
                f"{settings.gemini_base_url.rstrip('/')}/models/"
                f"{model_name}:generateContent?key={settings.gemini_api_key}"
            )
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=settings.gemini_timeout_seconds) as resp:
                    body = resp.read().decode("utf-8")
                if model_name != settings.gemini_model:
                    logger.info("Gemini fallback succeeded with model %s", model_name)
                return _parse_gemini_response(body)
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                wrapped = AgentError(f"Gemini API error {exc.code}: {err_body[:200]}")
                # Only fall through to the next model on transient capacity
                # errors. Hard-quota errors should bubble up immediately.
                if _is_hard_quota_error(wrapped) or exc.code in (400, 401, 403):
                    import app.agent.llm_client as llm_module
                    llm_module._last_request_failed_quota = True
                    raise wrapped from exc
                last_exc = wrapped
                logger.warning(
                    "Gemini model %s returned %d, trying next candidate: %s",
                    model_name, exc.code, _short(wrapped),
                )
                continue
            except urllib.error.URLError as exc:
                last_exc = AgentError(f"Gemini network error: {exc.reason}")
                logger.warning("Gemini model %s network error: %s", model_name, exc.reason)
                continue
        # All candidates exhausted.
        raise AgentError(
            f"Gemini all models failed (tried {len(candidates)}): {_short(last_exc)}"
        ) from last_exc


def _convert_to_gemini_contents(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Convert OpenAI-style messages to Gemini's contents[] format."""
    system_text = ""
    contents: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_text = msg.get("content") or ""
            continue
        if role == "user":
            contents.append({
                "role": "user",
                "parts": [{"text": msg.get("content") or ""}],
            })
        elif role == "assistant":
            # If we have the raw Gemini parts from a previous round (which
            # preserves thought_signature for function calls in Gemini 3.x),
            # pass them through verbatim.
            raw_parts = msg.get("raw_parts")
            if raw_parts:
                contents.append({"role": "model", "parts": raw_parts})
                continue
            parts: list[dict[str, Any]] = []
            text = msg.get("content") or ""
            if text:
                parts.append({"text": text})
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                args_raw = fn.get("arguments") or "{}"
                try:
                    args_obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args_obj = {}
                parts.append({"functionCall": {"name": fn.get("name"), "args": args_obj}})
            contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": msg.get("name") or "",
                        "response": {"result": msg.get("content") or ""},
                    },
                }],
            })
    return system_text, contents


def _convert_to_gemini_tools(tools: list[dict[str, Any]], system_text: str, contents: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert OpenAI-style tools list to Gemini tools spec."""
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        fn = tool.get("function") or {}
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        declarations.append({
            "name": fn.get("name") or "",
            "description": fn.get("description") or "",
            "parameters": _clean_schema(params),
        })
    payload: dict[str, Any] = {"contents": contents}
    if declarations:
        payload["tools"] = [{"function_declarations": declarations}]
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}
    return payload


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip unsupported JSON Schema fields for Gemini (e.g. additionalProperties)."""
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key in {"additionalProperties", "$schema", "title", "default",
               "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
               "multipleOf", "patternProperties", "minLength", "maxLength",
               "minItems", "maxItems", "uniqueItems"}:
            continue
        if isinstance(value, dict):
            value = _clean_schema(value)
        elif isinstance(value, list):
            value = [_clean_schema(item) if isinstance(item, dict) else item for item in value]
        cleaned[key] = value
    return cleaned