"""LLM client supporting the Gemini Free API with offline heuristic fallback."""

from __future__ import annotations

import json
import os
import random
import socket
import threading
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import AgentError, LLMTimeoutError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Transient-error retry policy (Gemini free tier: 429 rate limit, 503 capacity).
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CAP_SECONDS = 20.0

# Client-side throttle. The configured Gemini key is served by a proxy with a
# small requests-per-minute budget, so we serialise LLM calls and leave a gap
# between them instead of firing them back-to-back and burning the quota.
#
# WHY 0.5s and not 4s: a single agent chat makes SEVERAL LLM calls (one per
# tool-calling round). With a 4s gap, a 3-round conversation burned 8s of pure
# sleeping on top of the model latency, and the multi-round loop introduced
# here made that worse. The measured Gemini latency for this key is ~1-3s per
# call, so a 0.5s gap still keeps the calls from firing simultaneously while
# costing almost nothing.
#
# The throttle is a soft guard, not the quota control: if it turns out to be
# too aggressive the provider answers 429 and the retry/backoff path above
# handles it.
_MIN_INTERVAL_SECONDS = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "0.5"))
_request_lock = threading.Lock()
_last_request_at = 0.0
_last_request_failed_quota = False  # skip throttle after hard-quota failures

# Total wall-clock budget for ONE ``LLMClient.chat()`` call - i.e. for the
# whole candidate chain plus any retries.
#
# WHY THIS EXISTS: the per-candidate socket timeout alone was 25s and the
# chain had two candidates, so a provider hiccup cost 50s of the agent's 75s
# deadline before the offline fallback kicked in. Measured end to end: the
# walk-forward itself took 1.7s (it had already been moved to a child
# process), yet the chat took 52s - 50s of it waiting on Gemini sockets.
#
# The budget is enforced ACROSS candidates, so the chain stops early instead
# of spending the full timeout on every model in turn. A first candidate that
# hangs gets the lion's share; a second one only gets what is left.
LLM_CALL_BUDGET_SECONDS = float(os.getenv("LLM_CALL_BUDGET_SECONDS", "35"))

# A single candidate never gets the whole budget: at least this many seconds
# are reserved so that, if the first candidate fails fast, the fallback
# candidate still has a usable timeout.
_MIN_CANDIDATE_TIMEOUT_SECONDS = 8.0


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


def _is_timeout_reason(reason: object) -> bool:
    """True when a urllib error reason is really a timeout.

    ``urlopen`` wraps a socket timeout in ``URLError``, whose ``reason`` is
    either a ``TimeoutError`` or the string "timed out". Treating a timeout
    as a generic network error would skip the "try the next model" path and
    abort the whole chain on the FIRST slow candidate.
    """
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(reason).lower()


# Fallback chain for the Gemini free tier. When a model is overloaded
# ("experiencing high demand"), a sibling Flash model usually has capacity.
# Keep the list short — every extra candidate burns another HTTPS round-trip
# on the failure path.
#
# IMPORTANT (verified 2026-10-29 against this project's key): an alias that
# does not exist returns HTTP 404 immediately, but the "gemini-flash-latest"
# alias HANGS - the socket stays open for the full timeout without a single
# byte of response. A hanging candidate therefore costs the whole timeout
# before the chain can advance. Only concrete, immediately-answering model
# ids belong in this list; "gemini-3-flash" and "gemini-2.5-flash" are gone
# (404 "no longer available") and are deliberately NOT listed.
_GEMINI_FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
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

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        deadline: float | None = None,
    ) -> dict[str, Any]:
        provider = self._active_provider()
        if provider == "local":
            raise AgentError("No LLM provider is configured.")

        # Retry loop with exponential backoff + jitter. Gemini free tier is
        # aggressively rate-limited (429) and prone to capacity spikes (503),
        # both of which clear on their own after a short wait.
        #
        # ONE budget covers the whole method - the retries AND the candidate
        # chain inside each attempt. Without this, a provider outage cost
        # 4 attempts x 2 candidates x 25s = 200s, far past the agent's 75s
        # deadline. The budget makes the worst case bounded and predictable.
        last_exc: Exception | None = None
        if deadline is None:
            deadline = time.monotonic() + LLM_CALL_BUDGET_SECONDS
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if time.monotonic() >= deadline:
                logger.warning(
                    "LLM budget of %.0fs exhausted before attempt %d",
                    LLM_CALL_BUDGET_SECONDS,
                    attempt,
                )
                break
            _throttle()
            try:
                return self._chat_gemini(messages, tools, deadline)
            except Exception as exc:
                last_exc = exc
                # Every candidate model hung. Retrying would just re-hang on
                # the same models for another full timeout budget each time,
                # so fail over to the offline router immediately instead.
                if isinstance(exc, LLMTimeoutError):
                    logger.error(
                        "LLM request timed out on every candidate model: %s", _short(exc)
                    )
                    raise
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
                # Never sleep past the budget - a 20s backoff with 3s of
                # budget left would waste the remaining time on nothing.
                if time.monotonic() + delay >= deadline:
                    logger.warning(
                        "Transient LLM error (attempt %d/%d) but the %.0fs budget "
                        "would be exceeded by the %.1fs backoff; giving up.",
                        attempt,
                        _MAX_ATTEMPTS,
                        LLM_CALL_BUDGET_SECONDS,
                        delay,
                    )
                    break
                logger.warning(
                    "Transient LLM error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, _MAX_ATTEMPTS, delay, _short(exc),
                )
                time.sleep(delay)

        raise AgentError(f"LLM request failed: {_short(last_exc)}") from last_exc

    # ── Gemini Free API (Google AI Studio) ────────────────────────────────────
    def _chat_gemini(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        deadline: float | None = None,
    ) -> dict[str, Any]:
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

        # The budget covers the WHOLE chain, not each candidate. A hanging
        # first model must not be able to spend the full per-candidate
        # timeout before the fallback even starts.
        if deadline is None:
            deadline = time.monotonic() + LLM_CALL_BUDGET_SECONDS

        for index, model_name in enumerate(candidates):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "LLM budget of %.0fs exhausted before trying %s",
                    LLM_CALL_BUDGET_SECONDS,
                    model_name,
                )
                # Distinguish "the provider hung" from "we ran out of time
                # before we could even ask" - the caller treats a timeout
                # differently from a generic failure.
                if last_exc is None:
                    raise LLMTimeoutError(
                        f"Gemini budget of {LLM_CALL_BUDGET_SECONDS:.0f}s exhausted "
                        "before the first model was tried"
                    )
                break

            # Every candidate except the last one keeps a slice of the budget
            # in reserve, so a fast failure on model #1 still leaves model #2
            # a usable timeout instead of a fraction of a second.
            candidates_left = len(candidates) - index
            if candidates_left > 1:
                share = remaining / candidates_left
                candidate_timeout = max(_MIN_CANDIDATE_TIMEOUT_SECONDS, share)
            else:
                candidate_timeout = remaining
            # The reserved slice must never push the timeout past the budget.
            candidate_timeout = min(candidate_timeout, remaining)

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
                with urllib.request.urlopen(req, timeout=candidate_timeout) as resp:
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
                # A socket timeout raised by urllib is wrapped in URLError, so
                # it lands here rather than in the (TimeoutError, socket.timeout)
                # branch below. `isinstance` is checked because the reason may
                # be a plain timeout rather than a connection failure.
                if _is_timeout_reason(exc.reason):
                    last_exc = AgentError(f"Gemini model {model_name} timed out: {exc}")
                    logger.warning(
                        "Gemini model %s timed out after %.0fs, trying next candidate",
                        model_name,
                        candidate_timeout,
                    )
                    continue
                last_exc = AgentError(f"Gemini network error: {exc.reason}")
                logger.warning("Gemini model %s network error: %s", model_name, exc.reason)
                continue
            except (TimeoutError, socket.timeout) as exc:
                # A read timeout is NOT wrapped in URLError, so without this
                # branch it escapes the candidate loop entirely: one hanging
                # model aborts the whole fallback chain and the outer retry
                # loop restarts from the same first candidate. That is what
                # made a single chat take 250s before falling back offline.
                # Treat it like a transient capacity error and try the next
                # concrete model.
                last_exc = AgentError(f"Gemini model {model_name} timed out: {exc}")
                logger.warning(
                    "Gemini model %s timed out after %.0fs, trying next candidate",
                    model_name,
                    candidate_timeout,
                )
                continue
        # All candidates exhausted.
        if last_exc is not None and isinstance(last_exc, AgentError) and "timed out" in last_exc.message:
            raise LLMTimeoutError(
                f"Gemini all models timed out (tried {len(candidates)}): {_short(last_exc)}"
            ) from last_exc
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