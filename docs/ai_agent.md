# AI Agent

Agent dùng tool calling. LLM không được bịa dữ liệu - mọi con số đều phải lấy từ backend tools (chính là các API `/api/v1/...`).

## Tools có sẵn

| Tool | Mô tả |
|------|-------|
| `get_market_summary` | Tổng quan thị trường (symbol, giá mới nhất, % thay đổi) |
| `query_stock_data` | Lịch sử OHLCV theo khoảng thời gian |
| `calculate_indicators` | SMA / EMA / RSI / MACD / Bollinger Bands |
| `forecast_stock` | Dự báo N-day bằng Linear Regression / ARIMA / LSTM |
| `compare_models` | So sánh 3 model trên cùng 1 symbol |
| `run_backtest` | Chạy MA Crossover hoặc RSI Strategy |
| `walk_forward` | Walk-forward validation cho model |
| `get_news` | Tin tức mới nhất (Finnhub / Yahoo RSS) |
| `get_company_profile` | Thông tin công ty (Finnhub) |

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
| **OpenAI** | `OPENAI_API_KEY` | Không | Tốn phí, fallback option |
| **Local router** | (không cần) | Miễn phí | Auto-fallback khi không có key - vẫn gọi đúng tools |

```bash
# .env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<free-key-from-aistudio.google.com>
GEMINI_MODEL=gemini-2.0-flash-exp
```

## Local Tool Router (fallback)

Nếu `GEMINI_API_KEY` (và `OPENAI_API_KEY`) trống, agent tự dùng **local tool router**:

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
