"""Research AI agent with tool calling and an offline deterministic fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.llm_client import LLMClient
from app.agent.prompts import SYSTEM_PROMPT, PROJECT_CONTEXT
from app.agent.tool_registry import execute_tool, openai_tools
from app.core.constants import GLOBAL_SYMBOLS
from app.core.exceptions import AgentError, StockLakehouseError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class StockAnalysisAgent:
    """Never fabricates prices, indicators, forecasts, or backtest metrics."""

    def __init__(self) -> None:
        self.llm = LLMClient()

    def reply(self, user_message: str, default_symbol: str | None = None) -> dict[str, Any]:
        if self.llm.is_configured():
            try:
                return self._llm_reply(user_message, default_symbol)
            except Exception as exc:
                logger.warning("LLM path failed (%s). Falling back to local tool router.", exc)
        return self._local_reply(user_message, default_symbol)

    def _llm_reply(self, user_message: str, default_symbol: str | None) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        first = self.llm.chat(messages, openai_tools())
        tool_trace: list[dict[str, Any]] = []
        if first.get("tool_calls"):
            messages.append(
                {
                    "role": "assistant",
                    "content": first.get("content") or "",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["name"], "arguments": call["arguments"]},
                        }
                        for call in first["tool_calls"]
                    ],
                    # Preserve Gemini 3.x thought_signature on round-trip.
                    "raw_parts": first.get("raw_parts"),
                }
            )
            for call in first["tool_calls"]:
                try:
                    args = json.loads(call["arguments"] or "{}")
                    if "symbol" in args:
                        # Guard against the LLM inventing a ticker out of ordinary
                        # prose (e.g. "con AI này" -> CON). Only trust its symbol
                        # when the message actually looks like a market question.
                        if not _is_valid_ticker(args.get("symbol")) or not _wants_symbol_resolution(user_message):
                            args["symbol"] = default_symbol or "AAPL"
                    elif default_symbol:
                        args["symbol"] = default_symbol
                    result = execute_tool(call["name"], args)
                    error = None
                except StockLakehouseError as exc:
                    result = {"error": exc.message}
                    error = exc.message
                    args = {}
                tool_trace.append(
                    {"tool_name": call["name"], "tool_arguments": args, "tool_result": result, "error": error}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": json.dumps(result, default=str),
                    }
                )
            second = self.llm.chat(messages, openai_tools())
            if second and second.get("content"):
                content = second["content"]
            else:
                # Model didn't produce text after seeing tool results.
                # Synthesise a brief answer from the tool traces instead of
                # failing silently.
                tool_names = [t["tool_name"] for t in tool_trace]
                if "forecast_stock" in tool_names:
                    ft = next(t for t in tool_trace if t["tool_name"] == "forecast_stock")
                    r = ft.get("tool_result") or {}
                    metrics = r.get("metrics") or {}
                    result_symbol = r.get("symbol") or default_symbol or "AAPL"
                    model_name = r.get("model_name") or "model"
                    content = (
                        f"Dự báo **{model_name}** cho **{result_symbol}**: "
                        f"MAE={metrics.get('mae', 'N/A')}, RMSE={metrics.get('rmse', 'N/A')}, "
                        f"MAPE={metrics.get('mape', 'N/A')}%, "
                        f"Directional Accuracy={metrics.get('directional_accuracy', 'N/A')}%. "
                        f"{r.get('disclaimer', '')}"
                    )
                elif "run_backtest" in tool_names:
                    bt = next(t for t in tool_trace if t["tool_name"] == "run_backtest")
                    r = bt.get("tool_result") or {}
                    result_symbol = r.get("symbol") or default_symbol or "AAPL"
                    content = (
                        f"Backtest **{r.get('strategy', 'strategy')}** cho **{result_symbol}**: "
                        f"Total Return={r.get('total_return', 0):.2%}, "
                        f"Win Rate={r.get('win_rate', 0):.2%}, Sharpe={r.get('sharpe_ratio', 0):.2f}, "
                        f"Max Drawdown={r.get('maximum_drawdown', 0):.2%}, "
                        f"Trades={r.get('number_of_trades', 0)}. "
                        f"{r.get('disclaimer', '')}"
                    )
                elif "calculate_indicators" in tool_names:
                    ci = next(t for t in tool_trace if t["tool_name"] == "calculate_indicators")
                    r = ci.get("tool_result") or {}
                    content = (
                        f"Chỉ báo kỹ thuật: "
                        f"RSI={r.get('rsi')}, MACD={r.get('macd')}, "
                        f"SMA20={r.get('sma_20')}, SMA50={r.get('sma_50')}, "
                        f"EMA12={r.get('ema_12')}, EMA26={r.get('ema_26')}. "
                        f"{r.get('summary', {}).get('trend', '')}"
                    )
                elif "compare_models" in tool_names:
                    cm = next(t for t in tool_trace if t["tool_name"] == "compare_models")
                    r = cm.get("tool_result") or {}
                    lines = [f"So sánh model cho **{r.get('symbol', default_symbol or 'AAPL')}**:"]
                    for item in r.get("models") or []:
                        lines.append(
                            f"- {item.get('model_name')}: MAE={item.get('mae')}, "
                            f"RMSE={item.get('rmse')}, MAPE={item.get('mape')}%, "
                            f"DA={item.get('directional_accuracy')}%"
                        )
                    if not r.get("models"):
                        lines.append("Chưa có mô hình nào được train cho symbol này.")
                    content = "\n".join(lines)
                elif "query_stock_data" in tool_names or "get_market_summary" in tool_names:
                    qs = next((t for t in tool_trace if t["tool_name"] in ("query_stock_data", "get_market_summary")), None)
                    r = qs.get("tool_result") or {}
                    content = (
                        f"**{r.get('symbol', default_symbol or 'AAPL')}**: "
                        f"Close={r.get('last_close') or r.get('close')}, "
                        f"Change={r.get('change_pct', 0):.2%}, "
                        f"Volume={r.get('volume', 0):,.0f}."
                    )
                elif tool_trace:
                    content = f"Đã chạy tool thành công: {', '.join(tool_names)}."
                else:
                    content = "Không có dữ liệu trả về."
        else:
            content = first.get("content") or ""
            if not content:
                raise AgentError("LLM returned an empty response.")
        # Heuristic follow-ups: the LLM path can't cheaply ask the LLM
        # "give me 3 follow-ups", so we mirror the offline path's logic.
        return {
            "assistant_message": content,
            "tools": tool_trace,
            "suggested_questions": _follow_up_suggestions(
                default_symbol or "AAPL",
                [(t["tool_name"], t["tool_arguments"]) for t in tool_trace],
            ),
            "tool_count": len(tool_trace),
        }

    def _local_reply(self, user_message: str, default_symbol: str | None) -> dict[str, Any]:
        """Deterministic router so the thesis demo works without an API key.

        This is the offline fallback only. Chitchat / small-talk should
        normally be answered by the LLM. If we get here without an LLM,
        we fall back to a minimal answer that tells the user what we can
        do, plus a tool run if we can detect a finance intent.

        Supports multi-tool chaining: a single Vietnamese question can
        trigger both ``query_stock_data`` and ``calculate_indicators`` in
        one pass, so the offline demo matches what the LLM would have
        returned (fewer round-trips, richer answer).
        """
        text = user_message.lower()
        plan: list[tuple[str, dict[str, Any]]] = []

        # 1. Symbol: prefer what the user selected in the UI, then extract from message, then fallback.
        has_intent = _has_finance_intent(text)
        symbol = (
            _extract_symbol(user_message, default_symbol)
            if has_intent
            else (default_symbol or "AAPL").upper()
        )

        # 2. Respond to simple greetings without finance context
        if _is_greeting(text):
            greeting = (
                f"Xin chào! Mình là trợ lý phân tích chứng khoán. "
                f"Mã hiện tại: **{symbol}**. Bạn cần mình giúp gì?\n\n"
                "Ví dụ: \"phân tích AAPL\", \"backtest MSFT\", \"RSI VCB\", "
                "\"dự báo NVDA\", \"so sánh models GOOGL\"."
            )
            return {
                "assistant_message": greeting,
                "tools": [],
                "suggested_questions": _greeting_suggestions(symbol),
            }

        # 2b. Project / system question (offline mode) — call the matching
        # system_tools function and synthesise a Vietnamese answer from the
        # runtime data + PROJECT_CONTEXT. This mirrors what the LLM would do
        # when the API is reachable, so the demo works during a Gemini quota
        # outage as well.
        #
        # Priority: if the message has clear project intent, route to the
        # project handler EVEN if the generic finance-intent matcher fires
        # (some project questions contain the substring "model" or "kiến
        # trúc" which the finance matcher would otherwise misclassify).
        if _has_project_intent(text) and not _is_pure_finance_intent(text):
            return _handle_project_question(user_message, text)
        if not has_intent and _has_project_intent(text):
            return _handle_project_question(user_message, text)

        # 3. Intent-based tool routing.
        # We allow multi-tool plans: a single "phân tích VCB" fires both
        # market data + indicators in one call, so the demo feels responsive
        # even without the LLM summarising in a second pass.
        if any(word in text for word in ["so sánh", "compare", "mae", "rmse"]):
            plan.append(("compare_models", {"symbol": symbol}))
        elif any(word in text for word in ["dự báo", "forecast", "lstm", "arima", "linear"]):
            model = "lstm" if "lstm" in text else "arima" if "arima" in text else "linear_regression"
            plan.append(("forecast_stock", {"symbol": symbol, "model_name": model}))
        elif any(word in text for word in ["backtest", "walk-forward", "walkforward"]):
            strategy = "rsi_strategy" if "rsi" in text else "ma_crossover"
            plan.append(("run_backtest", {"symbol": symbol, "strategy": strategy}))
        elif any(word in text for word in ["tin tức", "tin tuc", "news", "sentiment"]):
            plan.append(("get_sentiment_summary", {"symbol": symbol}))
        elif any(
            word in text
            for word in ["rsi", "macd", "sma", "ema", "bollinger", "chỉ báo", "kỹ thuật"]
        ):
            # "Phân tích kỹ thuật VCB" — chain market data + indicators so
            # the assistant has both to summarise.
            plan.append(("query_stock_data", {"symbol": symbol}))
            plan.append(("calculate_indicators", {"symbol": symbol}))
        elif any(word in text for word in ["tài chính", "doanh thu", "lợi nhuận", "cổ tức", "fundamental"]):
            plan.append(("get_fundamental_metrics", {"symbol": symbol}))
        elif has_intent:
            # Generic intent (e.g. "phân tích VCB", "giá FPT", "thị trường") —
            # has intent but no specific tool keyword. Default to market summary.
            plan.append(("get_market_summary", {"symbol": symbol}))

        tools: list[dict[str, Any]] = []
        collected: dict[str, Any] = {}
        for name, args in plan:
            try:
                result = execute_tool(name, args)
                error = None
            except StockLakehouseError as exc:
                result = {"error": exc.message}
                error = exc.message
            tools.append({"tool_name": name, "tool_arguments": args, "tool_result": result, "error": error})
            collected[name] = result

        if not collected:
            # Pure non-finance message and the LLM is unavailable (rate limit /
            # outage). Answer naturally instead of leaking infrastructure detail.
            return {
                "assistant_message": _offline_smalltalk(user_message, symbol),
                "tools": [],
                "suggested_questions": _fallback_suggestions(symbol),
            }

        message = _render_local_answer(user_message, collected)
        return {
            "assistant_message": message,
            "tools": tools,
            "suggested_questions": _follow_up_suggestions(symbol, plan),
            "tool_count": len(plan),
        }

def _offline_smalltalk(user_message: str, symbol: str) -> str:
    """Friendly, non-repetitive reply used only while the LLM is unreachable.

    We must not pretend a model is answering, and we must not spam the same
    "no LLM configured" sentence on every message, so we vary the phrasing and
    point the user at something we *can* do (real backend data).
    """
    text = user_message.lower().strip()
    options = [
        (
            f"Phần mô hình ngôn ngữ đang tạm không dùng được (hết quota nhà cung cấp), "
            f"nhưng dữ liệu backend vẫn chạy tốt. Bạn thử hỏi: "
            f"\"phân tích kỹ thuật {symbol}\", \"RSI {symbol}\", \"backtest {symbol}\", "
            f"\"dự báo {symbol}\" nhé."
        ),
        (
            f"Mình không gọi được LLM lúc này nên chỉ chạy được tool dữ liệu thật: giá OHLCV, "
            f"chỉ báo kỹ thuật, backtest và dự báo cho {symbol}. Bạn muốn tra mã nào?"
        ),
        (
            f"Xin lỗi, LLM đang tạm không trả lời được. Để có kết quả ngay, hãy dùng lệnh cụ thể "
            f"như \"so sánh model {symbol}\" hoặc \"tin tức {symbol}\" — mình sẽ chạy tool lấy "
            f"số liệu thật từ lakehouse."
        ),
    ]
    # Deterministic-but-varied: hash the message so the same question does not
    # get a different answer each time, while different questions vary.
    index = sum(ord(ch) for ch in text) % len(options)
    return options[index]


def _is_greeting(text: str) -> bool:
    """Return True if the message is a simple greeting / chitchat.

    Must use word-boundary matching — bare substring checks are too greedy
    and would match greetings inside real questions like "hệ thống có bao
    nhiêu mã" (matches "có") or "MinIO có bao nhiêu file" (matches "có").
    """
    # Both diacritics and ASCII fallbacks — user input may arrive as
    # partially-normalised text ("xin chao" vs "xin chào").
    GREETING_PATTERNS = (
        "xin chào", "xin chao", "chào bạn", "chao ban",
        "chào buổi", "chao buoi", "chào anh", "chào chị",
        "hello", "hi", "hey", "alo",
        "good morning", "good afternoon", "good evening", "good day",
        "bạn khỏe không", "ban khoe khong",
        "bạn là ai", "ban la ai", "bạn là gì", "ban la gi",
        "giúp gì được", "giup gi duoc",
        "làm gì", "lam gi", "có gì", "co gi",
    )
    # Strip trailing punctuation to match bare words
    stripped = text.rstrip(".,!?;:").strip()
    # Try word-boundary match for each pattern so "có" inside "MinIO có" or
    # "hệ thống có" doesn't trip a false positive.
    for p in GREETING_PATTERNS:
        pattern = r"(^|\b)" + re.escape(p) + r"(\b|$)"
        if re.search(pattern, stripped):
            return True
    return False


def _wants_symbol_resolution(message: str) -> bool:
    """Return True when the user's text actually names a tradeable ticker.

    The LLM happily invents a ticker from ordinary words. We only let its
    symbol choice stand if the message also contains a known symbol, or if the
    user is clearly asking for market data.
    """
    upper = message.upper()
    if any(re.search(rf"\b{re.escape(s)}\b", upper) for s in GLOBAL_SYMBOLS):
        return True
    return _has_finance_intent(message.lower())


def _is_valid_ticker(symbol: object) -> bool:
    """Check whether a string is a real, supported ticker — not a noise word.

    We require membership in GLOBAL_SYMBOLS rather than a loose shape check.
    The shape check let prose words like "AI" (from "con AI này") or "CON" pass,
    which made tools run against symbols the lakehouse has never ingested.
    """
    if not isinstance(symbol, str):
        return False
    s = symbol.strip().upper()
    if not s:
        return False
    if s in GLOBAL_SYMBOLS:
        return True
    return False


def _extract_symbol(text: str, default_symbol: str | None) -> str:
    """Extract a ticker from a Vietnamese / English user question.

    We only ever return a symbol the lakehouse actually supports. Earlier
    versions fell back to "any 2-5 char uppercase token", which mis-read prose
    ("con AI này" -> AI, "cảm giác" -> CON) and fired tools against symbols
    that were never ingested. Better to fall back to the user's selection.
    """
    upper = text.upper()

    # Sort by length descending so longer tickers match first. "MA Crossover"
    # otherwise fires MA (Mastercard) before TSLA — short symbols are noise
    # inside compound words (MA, ON, SO, TD, …). We only trust longer names.
    for symbol in sorted(GLOBAL_SYMBOLS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(symbol)}\b", upper):
            return symbol

    fallback = (default_symbol or "AAPL").upper()
    return fallback if fallback in GLOBAL_SYMBOLS else "AAPL"


def _has_finance_intent(text: str) -> bool:
    """Return True if the user is asking about a stock, indicator, or model.

    Used as a guard so we don't accidentally fire a tool just because
    the message contains a stray uppercase token (e.g. "bạn khoẻ ko"
    contains "KO" but the user isn't asking about Coca-Cola).
    """
    keywords = (
        # Vietnamese intent (with and without diacritics — user input may arrive
        # as partially-normalised text, e.g. "phan tich" vs "phân tích")
        "phân tích", "phan tích", "phân tích", "giá", "giá",
        "tin tức", "tin tuc", "chỉ báo", "chi báo", "kỹ thuật", "ky thuat",
        "cổ phiếu", "co phieu", "cổ tức", "co tuc",
        "dự báo", "du bao", "backtest", "so sánh", "so sanh",
        "mô hình", "mo hinh", "lợi nhuận", "loi nhuan",
        "doanh thu", "doanh thu", "thị trường", "thi truong",
        "vn-index", "vnindex", "hose", "hnx",
        "khối lượng", "khoi luong", "thanh khoản", "thanh khoan",
        "tín hiệu", "tin hieu", "ngành", "nganh",
        "open", "close", "high", "low", "volume",
        # Indicators / models / strategies
        "rsi", "macd", "sma", "ema", "bollinger", "atr", "adx", "obv", "vwap", "stoch",
        "lstm", "arima", "linear", "regression", "xgboost", "model",
        "ma crossover", "crossover", "rsi strategy",
        # English verbs
        "analyze", "analyse", "price", "chart", "forecast",
        "compare", "backtest", "back-test", "show me", "tell me about",
        "what about", "how is", "how's",
    )
    for kw in keywords:
        if kw in text:
            return True
    return False


# "Pure" finance intent means the user is asking about a *specific* stock
# operation that should hit one of the 16 stock tools, NOT a generic
# project question. We require either a known ticker in the message or one
# of the more specific finance verbs. Bare "model" / "kiến trúc" / "công
# nghệ" are not enough — those belong to the project handler.
_PURE_FINANCE_KEYWORDS = (
    "rsi", "macd", "sma", "ema", "bollinger", "atr", "adx", "obv", "vwap", "stoch",
    "tin tức", "tin tuc", "chỉ báo", "chi báo", "kỹ thuật", "ky thuat",
    "phân tích kỹ thuật", "phan tich ky thuat",
    "dự báo", "du bao", "backtest", "walk-forward", "walkforward",
    "walk forward", "so sánh", "so sanh", "compare",
    "cổ tức", "co tuc", "tài chính", "doanh thu", "lợi nhuận",
    "forecast", "ma crossover", "crossover", "rsi strategy",
    "income statement", "balance sheet", "cash flow",
    "sentiment", "orderbook", "sổ lệnh", "so lenh",
    "chỉ số", "chi so", "vn-index", "vnindex", "^gspc", "^dji", "^ixic",
)


def _is_pure_finance_intent(text: str) -> bool:
    """True when the question is unambiguously about stock data, not the project.

    A question like "phân tích AAPL" or "RSI của VCB" returns True. A question
    like "đã train được những model nào?" or "kiến trúc hệ thống" returns
    False, even though the bare keyword matcher would catch them.
    """
    for kw in _PURE_FINANCE_KEYWORDS:
        if kw in text:
            return True
    # A real ticker mentioned alongside any finance intent is pure finance.
    sym = _extract_symbol(text, None)
    if sym and sym != "AAPL":
        return True
    return False


# ── Project / system question detection (used by the offline router) ────────
# When the LLM is unavailable (Gemini quota exhausted, no API key, network
# down) we still want the demo to be useful for questions about the platform
# itself. The user can ask "how many symbols?", "what's the architecture?",
# "which models are supported?" and the agent will call the matching
# ``system_tools`` function and render a Vietnamese answer from real data.

PROJECT_INTENT_KEYWORDS = (
    # Vietnamese
    "đồ án", "do an", "dự án", "du an", "hệ thống", "he thong", "hệ thống này",
    "kiến trúc", "kien truc", "cấu trúc", "cau truc",
    "stack", "công nghệ", "cong nghe", "tech stack",
    "có bao nhiêu mã", "bao nhieu ma", "tổng số mã", "tong so ma",
    "số mã", "so ma", "số lượng mã", "so luong ma",
    "mã nào", "ma nao", "những mã nào", "nhung ma nao",
    "theo dõi", "theo doi", "track", "supported",
    "đã train", "da train", "model đã train", "mo hinh da train",
    "mô hình nào", "mo hinh nao", "những model nào", "nhung model nao",
    "kiến trúc lakehouse", "kien truc lakehouse",
    "bronze", "silver", "gold",
    "minio", "minio có", "minio co", "file parquet", "dung lượng", "dung luong",
    "parquet", "csv",
    "walk-forward", "walk forward", "walkforward",
    "kafka", "iceberg", "spark", "fastapi", "minio", "mysql",
    "auto refresh", "auto-refresh", "auto refresh pipeline",
    "cấu hình", "cau hinh", "config", "configuration",
    "database gì", "database gi", "lưu trữ", "luu tru", "storage",
    "nguồn dữ liệu", "nguon du lieu", "data source", "data provider",
    "api nguồn", "api nguon", "providers",
    "bootstrap", "infrastructure", "hạ tầng", "ha tang",
    "việt nam", "viet nam", "hose", "hnx", "ssi", "iboard",
    "cổ phiếu việt", "co phieu viet",
    "mã việt", "ma viet",
    "hỗ trợ mã", "ho tro ma", "hỗ trợ cổ phiếu", "ho tro co phieu",
    "được hỗ trợ", "duoc ho tro",
    # English
    "architecture", "project", "system", "platform",
    "how many symbols", "how many stocks", "how many tickers",
    "which models", "what models", "trained models",
    "tech stack", "technology stack", "technologies",
    "data sources", "data providers",
    "what is this", "what is the", "explain the system",
    "tell me about the project", "tell me about the system",
    "about the project", "about the system", "about the platform",
)


def _has_project_intent(text: str) -> bool:
    """Return True if the user is asking about the platform itself.

    Project questions are about the *project* (architecture, models, symbols,
    tech stack) — distinct from *finance* questions about a specific stock.
    The two sets are intentionally disjoint: a "phân tích VCB" message should
    NOT be classified as project intent even if the user also asks "đồ án
    này dùng gì?".
    """
    for kw in PROJECT_INTENT_KEYWORDS:
        if kw in text:
            return True
    return False


def _handle_project_question(user_message: str, text: str) -> dict[str, Any]:
    """Run the matching system_tools call and synthesise a Vietnamese answer.

    Used by the offline router when the LLM is unreachable. Maps the
    detected project intent to a single ``system_tools`` function call, then
    composes a natural-language reply. Errors are surfaced as warnings, never
    fabricated.
    """
    from app.agent.tools.system_tools import (
        get_storage_stats,
        get_symbols_info,
        get_system_architecture,
        get_trained_models,
    )

    tool_name = "get_system_architecture"  # sensible default
    tool_args: dict[str, Any] = {}
    if any(kw in text for kw in ("mã", "ma", "symbol", "ticker", "track", "theo dõi", "theo doi")):
        tool_name = "get_symbols_info"
        if any(kw in text for kw in ("việt nam", "viet nam", "vn", "hose", "hnx", "ssi", "iboard")):
            tool_args = {"region": "vn"}
        elif any(kw in text for kw in ("us", "mỹ", "my", "american")):
            tool_args = {"region": "us"}
        elif any(kw in text for kw in ("crypto", "bitcoin", "btc")):
            tool_args = {"region": "crypto"}
        elif any(kw in text for kw in ("index", "chỉ số", "chi so", "s&p", "dow", "nasdaq")):
            tool_args = {"region": "index"}
    elif any(
        kw in text
        for kw in (
            "storage", "minio", "file", "parquet", "dung lượng", "dung luong",
            "object", "bucket", "layer",
        )
    ):
        # Storage question — only fire storage tool when the user is
        # clearly asking about storage, not when "layer" happens to be in
        # the message (it isn't normally).
        tool_name = "get_storage_stats"
        if any(kw in text for kw in ("bronze",)):
            tool_args = {"layer": "bronze"}
        elif any(kw in text for kw in ("silver",)):
            tool_args = {"layer": "silver"}
        elif any(kw in text for kw in ("gold",)):
            tool_args = {"layer": "gold"}
        elif "model" in text:
            tool_args = {"layer": "models"}
    elif any(
        kw in text
        for kw in (
            "train", "đã train", "da train", "mô hình nào", "mo hinh nao",
        )
    ):
        # "đã train được model nào" → trained models. Distinguish from
        # "đã train model VCB" (per-symbol) by looking for a ticker.
        tool_name = "get_trained_models"
        sym = _extract_symbol(user_message, None)
        if sym and sym != "AAPL":
            tool_args = {"symbol": sym}
    elif any(
        kw in text
        for kw in (
            "kiến trúc", "kien truc", "cấu trúc", "cau truc",
            "stack", "công nghệ", "cong nghe", "tech stack",
            "đồ án", "do an", "dự án", "du an", "hệ thống", "he thong",
        )
    ):
        tool_name = "get_system_architecture"
        # Detail level: "full" if user explicitly wants depth
        if any(kw in text for kw in ("chi tiết", "chi tiet", "đầy đủ", "day du", "full", "tất cả", "tat ca")):
            tool_args = {"detail_level": "full"}
        else:
            tool_args = {"detail_level": "summary"}

    try:
        tool_fn = {
            "get_symbols_info": get_symbols_info,
            "get_trained_models": get_trained_models,
            "get_system_architecture": get_system_architecture,
            "get_storage_stats": get_storage_stats,
        }[tool_name]
        result = tool_fn(**tool_args) if tool_args else tool_fn()
        error = None
    except Exception as exc:
        return {
            "assistant_message": (
                f"LLM tạm thời không khả dụng (hết quota nhà cung cấp) và tool hệ thống "
                f"cũng lỗi: {exc}. Bạn thử lại sau vài phút nhé."
            ),
            "tools": [
                {"tool_name": tool_name, "tool_arguments": tool_args, "tool_result": {"error": str(exc)}, "error": str(exc)}
            ],
            "suggested_questions": _project_suggestions(),
        }

    message = _render_project_answer(user_message, tool_name, result)
    return {
        "assistant_message": message,
        "tools": [
            {
                "tool_name": tool_name,
                "tool_arguments": tool_args,
                "tool_result": result,
                "error": None,
            }
        ],
        "suggested_questions": _project_suggestions(),
        "tool_count": 1,
    }


def _render_project_answer(question: str, tool_name: str, result: dict[str, Any]) -> str:
    """Synthesise a Vietnamese answer for a project question from tool data."""
    if isinstance(result, dict) and result.get("error"):
        return f"Tool `{tool_name}` lỗi: {result['error']}"

    lines: list[str] = [
        "Trả lời dựa trên dữ liệu runtime của hệ thống (tool calling) + PROJECT_CONTEXT.",
        "Lưu ý: đây là prototype nghiên cứu, không phải tư vấn đầu tư.",
        "",
    ]

    if tool_name == "get_symbols_info":
        total = result.get("total_symbols", 0)
        regions = result.get("regions", {})
        lines.append(
            f"Hệ thống đang theo dõi **{total} mã**, phân bổ như sau:"
        )
        lines.append(f"- US (blue-chips/mid-cap): {regions.get('us', 0)} mã")
        lines.append(f"- Toàn cầu (GLOBAL_SYMBOLS): {regions.get('global', 0)} mã")
        lines.append(f"- Chỉ số thị trường: {regions.get('market_indexes', 0)} mã")
        lines.append(f"- Crypto: {regions.get('crypto', 0)} mã")
        vn_list = regions.get("vn_top10_streamed", [])
        if vn_list:
            lines.append(f"- Việt Nam (stream realtime qua SSI iBoard): {', '.join(vn_list)}")
        if result.get("us_symbols_total"):
            lines.append("")
            lines.append(f"Một số mã US mẫu: {', '.join(result.get('sample_us_symbols', [])[:15])}")
        if result.get("vn_provider"):
            lines.append("")
            lines.append(f"Mã Việt Nam dùng provider: {result.get('vn_provider')}")
        notes = result.get("notes")
        if notes:
            lines.append("")
            lines.append(f"**Lưu ý**: {notes}")

    elif tool_name == "get_trained_models":
        sym_filter = result.get("filter_symbol")
        summary = result.get("summary", {})
        total = summary.get("total_models", 0)
        if sym_filter:
            lines.append(f"Model đã train cho **{sym_filter}**: {total} mô hình.")
        else:
            lines.append(
                f"Toàn hệ thống đã train **{total} mô hình** cho "
                f"**{summary.get('symbols_with_at_least_one_model', 0)} mã**."
            )
        by_name = summary.get("models_by_model_name", {})
        if by_name:
            lines.append("")
            lines.append("Phân bổ theo kiến trúc:")
            for name, count in sorted(by_name.items(), key=lambda kv: -kv[1]):
                lines.append(f"- {name}: {count} model")
        sample = summary.get("trained_symbols_sample") or []
        if sample:
            lines.append("")
            lines.append(f"Một số mã đã train (mẫu): {', '.join(sample)}")
        supported = result.get("model_architecture_supported", [])
        if supported:
            lines.append("")
            lines.append(f"Hệ thống hỗ trợ các kiến trúc: {', '.join(supported)}")
        models = result.get("models") or []
        if models:
            lines.append("")
            lines.append("Top models (MAE/RMSE/MAPE/DA):")
            for rec in models[:8]:
                lines.append(
                    f"- {rec.get('symbol', '?')} / {rec.get('model_name', '?')}: "
                    f"MAE={rec.get('mae')}, RMSE={rec.get('rmse')}, "
                    f"MAPE={rec.get('mape')}%, DA={rec.get('directional_accuracy')}%"
                )
        if total == 0:
            lines.append("")
            lines.append(
                "Chưa có mô hình nào được train. Hãy dùng endpoint "
                "`/api/v1/forecasting/train/{symbol}` để train model đầu tiên."
            )

    elif tool_name == "get_system_architecture":
        runtime = result.get("runtime", {})
        lines.append(f"**{result.get('project_name', 'Stock Lakehouse AI')}** — {result.get('purpose', '')}")
        layers = result.get("layers", {})
        for name, info in layers.items():
            lines.append(f"- **{name.upper()}**: {info.get('description', '')}")
        lines.append("")
        lines.append("**Data providers**: " + ", ".join(result.get("data_providers", [])))
        lines.append("**ML models**: " + ", ".join(result.get("models", [])))
        bt = result.get("backtesting", {})
        lines.append(
            f"**Backtest**: {', '.join(bt.get('strategies', []))} + "
            f"{bt.get('validation', '')}"
        )
        ts = result.get("tech_stack", {})
        lines.append("")
        lines.append("**Tech stack runtime**:")
        for k, v in ts.items():
            lines.append(f"- {k}: {v}")
        ar = result.get("auto_refresh", {})
        lines.append("")
        lines.append(
            f"**Auto-refresh**: chạy ngay khi startup "
            f"({'on' if ar.get('on_startup') else 'off'}), "
            f"sau đó mỗi {ar.get('interval_seconds', 0)//3600} giờ. "
            f"Phạm vi: {ar.get('scope', '')}"
        )
        lines.append("")
        lines.append(
            f"**Runtime hiện tại**: storage_backend=`{runtime.get('storage_backend', '?')}`, "
            f"data_source=`{runtime.get('data_source', '?')}`, "
            f"kafka=`{runtime.get('use_kafka')}`, "
            f"iceberg=`{runtime.get('use_iceberg')}`, "
            f"spark=`{runtime.get('use_spark')}`, "
            f"llm=`{runtime.get('llm_provider')}`"
        )
        lines.append(
            f"\nAgent có **{result.get('agent_tools_count', 0)} stock tools** + "
            "4 system tools (`get_symbols_info`, `get_trained_models`, "
            "`get_system_architecture`, `get_storage_stats`)."
        )
        if result.get("env_keys_relevant"):
            lines.append("")
            lines.append(
                "Env keys đáng quan tâm: "
                + ", ".join(result.get("env_keys_relevant", []))
            )
        vn_rt = result.get("vietnam_realtime")
        if vn_rt:
            lines.append("")
            lines.append(
                f"**VN realtime**: {vn_rt.get('ws_provider')} — boards: "
                f"{', '.join(vn_rt.get('boards', []))}"
            )
        disc = result.get("disclaimer")
        if disc:
            lines.append("")
            lines.append(f"*{disc}*")

    elif tool_name == "get_storage_stats":
        backend = result.get("storage_backend", "?")
        lines.append(f"**Storage backend hiện tại**: `{backend}`")
        buckets = result.get("buckets", {})
        if buckets:
            lines.append("")
            lines.append("Số object ở mỗi layer:")
            for name, stats in buckets.items():
                cnt = stats.get("count", -1)
                if cnt is None or cnt < 0:
                    lines.append(f"- {name}: lỗi ({stats.get('error', '?')})")
                else:
                    extra = ""
                    if "size_mb" in stats:
                        extra = f", {stats['size_mb']} MB"
                    lines.append(f"- {name}: {cnt} object{extra}")
        summary = result.get("summary", {})
        if summary.get("total_objects", 0) > 0:
            lines.append("")
            lines.append(
                f"**Tổng**: {summary['total_objects']} object trong "
                f"{summary.get('layers_with_data', 0)} layer(s) có dữ liệu."
            )
        live = result.get("live_counts") or {}
        if live:
            lines.append("")
            lines.append("Live counts (số symbol có ≥1 partition ở mỗi layer):")
            for k, v in live.items():
                lines.append(f"- {k}: {v}")
        if "mysql_connected" in result:
            lines.append("")
            lines.append(f"MySQL connected: {result['mysql_connected']}")

    else:
        lines.append(f"Kết quả tool `{tool_name}`: {json.dumps(result, ensure_ascii=False)[:1000]}")

    return "\n".join(lines)


def _project_suggestions() -> list[str]:
    return [
        "Đồ án này sử dụng những công nghệ gì?",
        "Hệ thống có bao nhiêu mã cổ phiếu?",
        "Đã train được những model nào?",
        "MinIO đang lưu trữ bao nhiêu file?",
    ]


def _render_local_answer(question: str, collected: dict[str, Any]) -> str:
    lines = [
        "Đây là câu trả lời dựa trên dữ liệu thật từ backend (tool calling).",
        "Kết quả chỉ phục vụ nghiên cứu học thuật, không phải khuyến nghị đầu tư.",
        "",
    ]
    for name, result in collected.items():
        if isinstance(result, dict) and result.get("error"):
            lines.append(f"Tool `{name}` thất bại: {result['error']}")
            continue
        if name == "calculate_indicators":
            lines.append(
                f"RSI={result.get('rsi')}, MACD={result.get('macd')}, "
                f"SMA20={result.get('sma_20')}, SMA50={result.get('sma_50')}."
            )
            summary = result.get("summary") or {}
            for key, value in summary.items():
                lines.append(f"{key}: {value}")
        elif name == "run_backtest":
            lines.append(
                f"Backtest {result.get('strategy')} cho {result.get('symbol')}: "
                f"Total Return={result.get('total_return'):.4f}, "
                f"Win Rate={result.get('win_rate'):.4f}, "
                f"Sharpe={result.get('sharpe_ratio'):.4f}, "
                f"Max Drawdown={result.get('maximum_drawdown'):.4f}, "
                f"Trades={result.get('number_of_trades')}."
            )
            lines.append(result.get("disclaimer", ""))
        elif name == "forecast_stock":
            metrics = result.get("metrics") or {}
            lines.append(
                f"Dự báo {result.get('model_name')} cho {result.get('symbol')}: "
                f"MAE={metrics.get('mae')}, RMSE={metrics.get('rmse')}, "
                f"MAPE={metrics.get('mape')}, Directional Accuracy={metrics.get('directional_accuracy')}."
            )
            if result.get("latest_predicted") is not None:
                lines.append(f"Giá trị dự báo gần nhất: {result['latest_predicted']:.4f}.")
            lines.append(result.get("disclaimer", ""))
        elif name == "compare_models":
            lines.append(f"So sánh mô hình cho {result.get('symbol')}:")
            for item in result.get("models") or []:
                lines.append(
                    f"- {item.get('model_name')}: MAE={item.get('mae')}, RMSE={item.get('rmse')}, "
                    f"MAPE={item.get('mape')}, DA={item.get('directional_accuracy')}"
                )
            if not result.get("models"):
                lines.append("Chưa có mô hình nào được train. Hãy train model trước.")
        elif name in {"query_stock_data", "get_market_summary"}:
            close = result.get("last_close") or result.get("close")
            change = result.get("change_pct")
            lines.append(
                f"{result.get('symbol')} close={close}, change={change}, volume={result.get('volume')}."
            )
        elif name == "get_sentiment_summary":
            pos = result.get("positive_count") or result.get("positive") or 0
            neg = result.get("negative_count") or result.get("negative") or 0
            neu = result.get("neutral_count") or result.get("neutral") or 0
            score = result.get("avg_sentiment") or result.get("sentiment_score")
            sym = result.get("symbol", symbol)
            lines.append(f"Sentiment tổng hợp {sym}: tích cực={pos}, tiêu cực={neg}, trung tính={neu}.")
            if score is not None:
                lines.append(f"Điểm sentiment trung bình: {score:.3f} (thang -1..1).")
        elif name == "get_fundamental_metrics":
            sym = result.get("symbol", symbol)
            metrics = result.get("metrics") or {}
            if metrics:
                # Surface the most thesis-relevant ratios first; keep the
                # English ticker names so the demo matches the report.
                ordered = ["pe_ratio", "pb_ratio", "roe", "roa",
                           "debt_to_equity", "dividend_yield", "eps"]
                for key in ordered:
                    if key in metrics and metrics[key] is not None:
                        lines.append(f"{key} = {metrics[key]}")
            else:
                lines.append(f"Chưa có metrics tài chính cho {sym}.")
    return "\n".join(lines)


# ── Suggested follow-up questions ─────────────────────────────────────────────
# We surface 3-4 prompts after every assistant message so the demo never
# gets stuck on "what now?" — even on the offline / rate-limited path.
# Questions are in Vietnamese (UI default) and keep English tickers + the
# English technical terms (RSI, MAE, MA Crossover, LSTM, …) intact, per
# the thesis writing convention.

def _greeting_suggestions(symbol: str) -> list[str]:
    return [
        f"Phân tích kỹ thuật {symbol}",
        f"So sánh 3 model cho {symbol}",
        f"Backtest MA Crossover cho {symbol}",
        f"Tin tức & sentiment {symbol}",
    ]


def _fallback_suggestions(symbol: str) -> list[str]:
    return [
        f"Phân tích kỹ thuật {symbol}",
        f"RSI và MACD của {symbol}",
        f"Dự báo {symbol} bằng LSTM",
        f"So sánh model {symbol}",
    ]


def _follow_up_suggestions(symbol: str, plan: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Return follow-up questions tailored to what was just executed.

    Each plan entry was already a (tool_name, args) tuple. We map the
    executed tool to a couple of natural next questions the user might
    want to drill into. ``plan`` may be empty (pure chitchat) — in that
    case we fall back to the greeting suggestions.
    """
    if not plan:
        return _greeting_suggestions(symbol)
    tool_names = {name for name, _ in plan}
    # Pick a "primary" tool — first non-fallback plan entry — for the
    # best match. Order matters because some tool names co-occur
    # (query_stock_data + calculate_indicators).
    primary = next(
        (name for name in ("compare_models", "forecast_stock", "run_backtest",
                           "calculate_indicators", "query_stock_data",
                           "get_market_summary", "get_sentiment_summary",
                           "get_fundamental_metrics")
         if name in tool_names),
        plan[0][0],
    )
    table: dict[str, list[str]] = {
        "compare_models": [
            f"Dự báo {symbol} bằng LSTM",
            f"Backtest MA Crossover cho {symbol}",
            f"Phân tích kỹ thuật {symbol}",
        ],
        "forecast_stock": [
            f"So sánh model {symbol}",
            f"Backtest MA Crossover cho {symbol}",
            f"RSI của {symbol} hiện tại",
        ],
        "run_backtest": [
            f"Walk-forward validation {symbol}",
            f"RSI Strategy cho {symbol}",
            f"Phân tích kỹ thuật {symbol}",
        ],
        "calculate_indicators": [
            f"Dự báo {symbol} bằng LSTM",
            f"So sánh model {symbol}",
            f"Backtest MA Crossover cho {symbol}",
        ],
        "query_stock_data": [
            f"Tính RSI và MACD cho {symbol}",
            f"Dự báo {symbol} bằng LSTM",
            f"Backtest MA Crossover cho {symbol}",
        ],
        "get_market_summary": [
            f"Tính RSI và MACD cho {symbol}",
            f"Phân tích kỹ thuật {symbol}",
            f"So sánh model {symbol}",
        ],
        "get_sentiment_summary": [
            f"Phân tích kỹ thuật {symbol}",
            f"Dự báo {symbol} bằng LSTM",
            f"Báo cáo tài chính {symbol}",
        ],
        "get_fundamental_metrics": [
            f"So sánh model {symbol}",
            f"Backtest MA Crossover cho {symbol}",
            f"Tin tức & sentiment {symbol}",
        ],
    }
    return table.get(primary, _greeting_suggestions(symbol))
