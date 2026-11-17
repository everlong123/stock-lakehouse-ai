# AI Agent

Agent dùng tool calling. LLM không được bịa dữ liệu - mọi con số đều phải lấy từ backend tools (chính là các API `/api/v1/...`).

## Tools có sẵn (17 tool, đo ngày 12/11/2026)

| Tool | Mô tả |
|------|-------|
| `query_stock_data` | Lịch sử OHLCV theo khoảng thời gian |
| `get_market_summary` | Tổng quan thị trường (symbol, giá mới nhất, % thay đổi) |
| `calculate_indicators` | SMA / EMA / RSI / MACD / Bollinger Bands |
| `forecast_stock` | Dự báo N-day bằng Linear Regression / ARIMA / LSTM |
| `compare_models` | So sánh 3 model trên cùng 1 symbol |
| `run_backtest` | Chạy MA Crossover hoặc RSI Strategy |
| `run_walk_forward` | Walk-forward validation cho model |
| `get_fundamental_metrics` | P/E, P/B, ROE, ROA... |
| `get_income_statement` | Báo cáo thu nhập |
| `get_balance_sheet` | Bảng cân đối kế toán |
| `get_cash_flow` | Báo cáo lưu chuyển tiền tệ |
| `get_market_index` | Chỉ số US (S&P 500, Dow, Nasdaq) |
| `get_orderbook` | Sổ lệnh bid/ask |
| `get_symbols_info` | Thống kê số mã hệ thống hỗ trợ |
| `get_trained_models` | Liệt kê model ML đã train |
| `get_system_architecture` | Kiến trúc runtime của hệ thống |
| `get_storage_stats` | Số object + dung lượng từng bucket MinIO |

> **Ghi chú 12/11/2026:** tool `get_news_for_symbol` và 3 tool sentiment đi kèm đã bị **gỡ
> khỏi dự án** cùng toàn bộ hệ thống tin tức (trước đó là 21 tool, nay còn **17 tool**).
> Chi tiết ở mục 5B.1 của `docs/HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md`.

Mỗi tool có Pydantic input/output schema riêng.

## System prompt

```
Bạn là trợ lý phân tích chứng khoán phục vụ mục đích nghiên cứu và học thuật.
Các kết quả phân tích và dự báo không phải khuyến nghị đầu tư.
```

## LLM Provider (chọn 1 trong `.env`)

| Provider | Key | Free? | Ghi chú |
|----------|-----|-------|---------|
| **Gemini** | `GEMINI_API_KEY` | Có (60 req/min) | Khuyến nghị - lấy key tại <https://aistudio.google.com/apikey> |
| **Local router** | (không cần) | Miễn phí | Auto-fallback khi không có key - vẫn gọi đúng tools |

```bash
# .env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<free-key-from-aistudio.google.com>
GEMINI_MODEL=gemini-2.0-flash-exp
```

## Local Tool Router (fallback)

Nếu `GEMINI_API_KEY` trống, agent tự dùng **local tool router**:

- Phân tích câu hỏi bằng keyword matching.
- Chọn tool phù hợp, gọi backend API.
- Compose câu trả lời từ kết quả tool.

Vẫn **không bịa số** - mọi con số đều từ backend. Chỉ khác là câu trả lời không đi qua LLM sinh tự do.

## Lịch sử chat

Lưu vào MySQL bảng `agent_conversations`:

- `session_id` (UUID)
- `user_message`
- `assistant_message`
- `tool_name` (tool đã gọi)
- `tool_arguments` (input JSON)
- `tool_result` (output JSON)
- `created_at`

## API

`POST /api/v1/agent/chat`

```json
{
  "session_id": "uuid-or-null",
  "message": "RSI hiện tại của VCB là bao nhiêu?"
}
```

Response:

```json
{
  "session_id": "uuid",
  "reply": "...",
  "tool_used": "calculate_indicators",
  "tool_result": {...}
}
```

## Test headless

```powershell
python scripts\run_agent.py --symbol VCB --question "RSI hiện tại bao nhiêu?"
```

Hoặc mở <http://127.0.0.1:5173/agent> trong browser để chat trực tiếp với Agent.
