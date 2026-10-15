"""Research AI agent with tool calling and an offline deterministic fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.llm_client import LLMClient
from app.agent.prompts import SYSTEM_PROMPT
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
    """Return True if the message is a simple greeting / chitchat."""
    # Both diacritics and ASCII fallbacks — user input may arrive as
    # partially-normalised text ("xin chao" vs "xin chào").
    GREETING_PATTERNS = (
        "xin chào", "xin chao", "chào", "chao", "hello", "hi", "hey",
        "alo", "chào buổi", "chao buoi",
        "good morning", "good afternoon", "good evening", "good day",
        "bạn khỏe không", "ban khoe khong", "bạn là ai", "ban la ai",
        "giúp gì được", "giup gi duoc", "làm gì", "lam gi", "có gì", "co gi",
    )
    # Strip trailing punctuation to match bare words
    stripped = text.rstrip(".,!?;:")
    return any(p in stripped for p in GREETING_PATTERNS)


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
