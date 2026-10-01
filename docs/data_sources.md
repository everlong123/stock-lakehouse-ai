# Free Data Sources

This document lists the **free** data sources configured for the Stock Lakehouse AI
project, their limits, and how to switch between them. All providers return
**real OHLCV market data** - there is no offline / synthetic fallback in the
ingestion pipeline (UI có synthetic fallback chỉ khi Lakehouse trống, xem `docs/lakehouse.md`).

---

## Quick comparison

| Provider           | Key required | Free tier limit                | Historical depth | Status      |
|--------------------|--------------|--------------------------------|------------------|-------------|
| **yfinance**       | No           | Unlimited (rate-limited)       | 10+ years        | Active      |
| **Finnhub REST**   | Yes          | 60 req/min                     | Years            | Active      |
| **Alpha Vantage**  | Yes          | 25 req/day                     | Last 100 days    | Active      |
| **SSI iBoard**     | No           | Public API (best-effort)       | 8-10 years VN    | Active      |
| **Web scraper**    | No           | Best-effort                    | Varies           | Backup      |
| **Multi-source**   | Auto         | Failover chain                 | Best of all      | Default     |

---

## 1. yfinance (best for deep historical, default)

- **Free tier:** unlimited (Yahoo rate-limit kicks in aggressively từ cloud / VPN IPs - trả empty DataFrame).
- **Historical depth:** 10+ years.
- **No key required.**
- **Config:** không cần - dùng `yfinance` Python package trực tiếp.

```bash
python scripts/ingest_historical.py --source yfinance --symbols AAPL --interval 1d
```

Nếu `yfinance` bị block, đổi sang `multi_source` (auto failover).

Đã upgrade lên `yfinance>=1.0` + `curl_cffi>=0.15` để bypass Yahoo TLS fingerprint block.

---

## 2. Finnhub (REST + WebSocket)

- **Free tier:** 60 requests / minute.
- **Endpoints:**
  - `/stock/candle` - up to years of OHLCV.
  - `/news`, `/stock/profile2` - news + company profile.
- **Register:** <https://finnhub.io/>
- **Config:** set `FINNHUB_API_KEY=...` trong `.env`.

```bash
python scripts/ingest_historical.py --source finnhub --symbols AAPL --interval 1d
```

**WebSocket** (free tier): 50 symbols / connection, ~50 msgs/sec. Dùng cho real-time streaming qua `scripts/run_stream_publisher.py`.

---

## 3. Alpha Vantage (daily fallback)

- **Free tier:** 25 requests / day.
- **Endpoints:**
  - `TIME_SERIES_DAILY` - last 100 daily bars.
  - `GLOBAL_QUOTE` - latest quote.
- **Register:** <https://www.alphavantage.co/support/#api-key>
- **Config:** set `ALPHA_VANTAGE_API_KEY=...` trong `.env`.

```bash
python scripts/ingest_historical.py --source alpha_vantage --symbols AAPL,MSFT --interval 1d
```

---

## 4. SSI iBoard (Vietnamese stocks)

- **Free tier:** public API, không cần key.
- **Coverage:** HOSE, HNX, UPCOM - 53 symbols phổ biến.
- **Endpoint:** `https://iboard-api.ssi.com.vn/statistics/charts/history`.
- **Historical depth:** 5-10 năm (xem `docs/vn_data_quality.md`).

```bash
python scripts/ingest_vn.py --years 10
```

SSI trả giá theo đơn vị nghìn VND - `SSIVNProvider._normalize()` tự multiply 1000.

---

## 5. Web scraper (no-key fallback)

Direct HTTP scrape Yahoo Finance / CafeF pages. Không cần key nhưng throughput thấp và dễ vỡ layout. Chỉ dùng khi các provider trên đều fail.

```bash
python scripts/ingest_historical.py --source web_scraper --symbols AAPL --interval 1d
```

---

## 6. Multi-source (default trong `.env`)

Auto failover chain - thử từng provider đến khi có data. Chain config trong `backend/app/data_sources/multi_source.py`:

```python
DEFAULT_CHAINS = {
    "1d":  ["yfinance", "finnhub", "yfinance_direct", "alpha_vantage"],
    "1h":  ["yfinance", "yfinance_direct", "finnhub"],
    "15m": ["yfinance", "yfinance_direct", "finnhub"],
    "5m":  ["yfinance", "yfinance_direct"],
}
```

```bash
python scripts/ingest_historical.py --source multi_source --symbols AAPL --interval 1d
```

Nếu yfinance bị block và Finnhub key invalid, chain silently fall through Alpha Vantage / web_scraper.

---

## Switching sources

Active source điều khiển qua `DATA_SOURCE` trong `.env`:

```env
DATA_SOURCE=multi_source   # default
DATA_SOURCE=yfinance
DATA_SOURCE=finnhub
DATA_SOURCE=alpha_vantage
DATA_SOURCE=web_scraper
```

Hoặc override per-run:

```bash
python scripts/ingest_historical.py --source alpha_vantage --symbols AAPL --interval 1d
```

---

## Recommended setup cho KLTN ($0 budget)

```env
DATA_SOURCE=multi_source
ALPHA_VANTAGE_API_KEY=<free-key>        # fallback daily
FINNHUB_API_KEY=<free-key>              # fallback + WebSocket streaming
# yfinance không cần key, đã có trong requirements.txt
```

Với `multi_source`, pipeline luôn tìm được 1 provider hoạt động.
