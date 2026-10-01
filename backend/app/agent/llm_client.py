"""LLM client supporting OpenAI, Gemini Free API, and offline heuristic fallback."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.exceptions import AgentError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


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
        if explicit == "openai" and settings.openai_api_key.strip():
            return "openai"
        if explicit == "local":
            return "local"
        # Auto-detect
        if settings.gemini_api_key.strip():
            return "gemini"
        if settings.openai_api_key.strip():
            return "openai"
        return "local"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        provider = self._active_provider()
        if provider == "local":
            raise AgentError("No LLM provider is configured.")
        try:
            if provider == "gemini":
                return self._chat_gemini(messages, tools)
            return self._chat_openai(messages, tools)
        except Exception as exc:
            logger.exception("LLM request failed (%s)", provider)
            raise AgentError(f"LLM request failed: {exc}") from exc

    # ── OpenAI-compatible (works for OpenAI, OpenAI-compatible routers) ───────
    def _chat_openai(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout_seconds,
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
        )
        message = response.choices[0].message
        tool_calls = []
        if message.tool_calls:
            for call in message.tool_calls:
                tool_calls.append({
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                })
        return {"content": message.content or "", "tool_calls": tool_calls}

    # ── Gemini Free API (Google AI Studio) ────────────────────────────────────
    def _chat_gemini(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        import urllib.request
        import urllib.error

        # Convert OpenAI-style messages to Gemini contents format
        system_text, contents = _convert_to_gemini_contents(messages)
        # Convert tools to Gemini function declarations
        gemini_tools = _convert_to_gemini_tools(tools, system_text)

        url = (
            f"{settings.gemini_base_url.rstrip('/')}/models/"
            f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
        )
        payload = json.dumps(gemini_tools).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=settings.openai_timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise AgentError(f"Gemini API error {exc.code}: {err_body[:200]}") from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"Gemini network error: {exc.reason}") from exc

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

        return {"content": "\n".join(text_parts), "tool_calls": tool_calls}


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
                "role": "function",
                "parts": [{
                    "functionResponse": {
                        "name": msg.get("name") or "",
                        "response": {"result": msg.get("content") or ""},
                    },
                }],
            })
    return system_text, contents


def _convert_to_gemini_tools(tools: list[dict[str, Any]], system_text: str) -> dict[str, Any]:
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
    payload: dict[str, Any] = {"contents": []}
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
        if key in {"additionalProperties", "$schema", "title", "default"}:
            continue
        if isinstance(value, dict):
            value = _clean_schema(value)
        elif isinstance(value, list):
            value = [_clean_schema(item) if isinstance(item, dict) else item for item in value]
        cleaned[key] = value
    return cleaned