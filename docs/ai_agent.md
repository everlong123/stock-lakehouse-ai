# AI Agent

Agent dùng tool calling. LLM không được bịa dữ liệu.

Tools:

- query_stock_data
- calculate_indicators
- forecast_stock
- compare_models
- run_backtest
- get_market_summary

Mỗi tool có Pydantic input/output schema.

System prompt:

> Bạn là trợ lý phân tích chứng khoán phục vụ mục đích nghiên cứu và học thuật. Các kết quả phân tích và dự báo không phải khuyến nghị đầu tư.

Nếu `OPENAI_API_KEY` trống, agent dùng local tool router: vẫn gọi đúng backend tools, không bịa số.

Lịch sử chat lưu MySQL `agent_conversations`.
