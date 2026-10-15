# Streaming Pipeline

Tài liệu mô tả cách dữ liệu giá cổ phiếu chảy từ nguồn ngoài vào Bronze/Silver/Gold.

## Tổng quan nguồn dữ liệu

| Thị trường | Nguồn | Loại | Interval | Real-time | Phí | Auth |
|---|---|---|---|---|---|---|
| US | `FinnhubWebSocket` (WebSocket) | tick → OHLCV 1s | per-second | ✅ | Free (50 subs, ~50 msg/s) | API key |
| US | `YFinanceEodPoller` (REST poll) | 1d bar | 1h | ❌ EOD | Free | Không cần |
| US | `FinnhubRestPoller` (REST poll) | 1m bar | 60s | ~ | **Paid only** (free tier đã cắt 2025-04) | API key |
| VN | `VNStreamPublisher` (SSI WebSocket) | tick → OHLCV 1s | per-second | ✅ | Free | Không cần |
| VN | `SSIVNProvider` (REST) | 1d bar | on-demand | ❌ EOD | Free | Không cần |

## Luồng dữ liệu

```
┌─────────────────┐   ┌──────────────────┐   ┌─────────────────┐
│ Finnhub WS (US) │   │  YFinanceEod     │   │ SSI WS (VN)     │
│  real-time tick │   │  1d bar poll     │   │  real-time tick │
└────────┬────────┘   └────────┬─────────┘   └────────┬────────┘
         │                     │                      │
         └──────────┬──────────┴──────────────────────┘
                    ▼
        ┌─────────────────────────┐
        │  Kafka topic            │
        │  "stock-ohlcv-raw"      │
        └────────┬────────────────┘
                 ▼
        ┌─────────────────────────┐
        │  KafkaConsumer          │
        │  (Bronze/Silver append) │
        └────────┬────────────────┘
                 ▼
        ┌─────────────────────────┐
        │  Bronze → Silver → Gold │
        └─────────────────────────┘
```

Mọi bar từ mọi nguồn đều được gắn `source` để truy vết:
- `finnhub_ws` — real-time tick từ Finnhub WebSocket
- `finnhub_rest` — 1m bar từ Finnhub REST (chỉ bật khi có paid plan)
- `yfinance_eod` — 1d bar từ yfinance
- `ssi_ws` — real-time tick từ SSI iBoard WebSocket

## Cấu hình (file `backend/.env`)

```ini
# US real-time (giữ nguyên)
FINNHUB_API_KEY=...

# US EOD poller (mới — bật để backfill 1d bars)
US_EOD_POLLER_ENABLED=true|false          # default false
US_EOD_POLLER_INTERVAL_SECONDS=3600       # 1h
US_EOD_POLLER_SYMBOLS=AAPL,MSFT,NVDA,TSLA,GOOGL

# Finnhub REST poller (chỉ bật nếu có paid plan)
US_REST_POLLER_ENABLED=true|false          # default false

# VN real-time (giữ nguyên)
VN_WS_ENABLED=true|false                   # default true
VN_WS_SYMBOLS=FPT,VNM,VCB,HPG,...
```

## Vận hành thủ công

```bash
# 1. Smoke-test yfinance (không cần Kafka)
cd backend
python -m scripts.test_yfinance_eod --symbol AAPL

# 2. Chạy 1 tick rồi in ra (không cần Kafka)
python -m app.streaming.yfinance_eod_poller --once --symbols AAPL,MSFT

# 3. Chạy US real-time trong 60s
python -m app.streaming.stream_publisher --symbols AAPL,MSFT --duration 60

# 4. Chạy VN real-time trong 30s (trong giờ HOSE)
python -m app.streaming.vn_websocket --symbols FPT --duration 30
```

## Khi nào có data?

| Sàn | Giờ mở cửa (giờ VN) | Real-time? |
|---|---|---|
| NYSE / NASDAQ | T2-T6, 15:30 - 22:00 | ✅ Finnhub WS |
| HOSE | T2-T6, 9:00 - 15:00 | ✅ SSI WS |
| Ngoài giờ + cuối tuần + lễ | — | ❌, EOD poller vẫn chạy |

Trong giờ sàn mở, demo tick chảy về mỗi ~1s. Ngoài giờ, đợi đến tick EOD tiếp theo (tối đa 1h sau khi sàn US đóng = ~4:00 sáng hôm sau theo giờ VN).

## Tại sao đổi sang yfinance?

Finnhub free tier **đã cắt** `/stock/candle` endpoint từ 2025-04-15
([GitHub issue #546](https://github.com/finnhubio/Finnhub-API/issues/546)).
Trước đó `FinnhubRestPoller` đang fail lặng lẽ với HTTP 401, không tạo ra
bar nào. `YFinanceEodPoller` thay thế vì:
- **Free**, không rate-limit
- Đã có `yfinance` package trong `requirements.txt`
- WebSocket Finnhub vẫn chạy bình thường (chỉ REST mới bị cắt)
