# Free Data Sources

This document lists the **free** data sources configured for the Stock Lakehouse AI
project, their limits, and how to switch between them.  All providers return
**real OHLCV market data** - there is no offline / synthetic fallback.

---

## Quick comparison

| Provider           | Key required | Free tier limit                | Historical depth | Status      |
|--------------------|--------------|--------------------------------|------------------|-------------|
| **Alpha Vantage**  | Yes          | 25 req/day                     | Last 100 days    | Active      |
| **Finnhub REST**   | Yes          | 60 req/min                     | Years            | Key old     |
| **yfinance**       | No           | Unlimited (rate-limited)       | 10+ years        | Blocked     |
| **Web scraper**    | No           | Best-effort                    | Varies           | Backup      |
| **Multi-source**   | Auto         | Failover chain                 | Best of all      | Default     |

---

## 1. Alpha Vantage (recommended default for KLTN)

- **Free tier:** 25 requests / day (enough for historical backfill runs)
- **Endpoints:**
  - `TIME_SERIES_DAILY` — last 100 daily bars (free, **not** the adjusted variant)
  - `TIME_SERIES_INTRADAY` — last 100 intraday bars at 5/15/30/60 min
  - `GLOBAL_QUOTE` — single latest quote
- **Register:** <https://www.alphavantage.co/support/#api-key>
- **Config:** set `ALPHA_VANTAGE_API_KEY=...` in `.env`
- **Use:**

```bash
python scripts/ingest_historical.py --source alpha_vantage --symbols AAPL,MSFT --interval 1d
```

---

## 2. Finnhub (REST, not WebSocket)

- **Free tier:** 60 requests / minute
- **Endpoints:** `/stock/candle` returns up to years of OHLCV
- **Register:** <https://finnhub.io/>
- **Config:** set `FINNHUB_API_KEY=...` in `.env`
- **Use:**

```bash
python scripts/ingest_historical.py --source finnhub --symbols AAPL --interval 1d
```

> **Note:** the project's WebSocket streaming layer is optional and currently
> disabled.  This document only covers historical (REST) sources.

---

## 3. yfinance (best for deep historical)

- **Free tier:** unlimited (Yahoo's rate limit kicks in aggressively from
  cloud / VPN IPs - returns empty DataFrames for unknown reasons)
- **Historical depth:** 10+ years
- **No key required.**
- **Config:** none - uses the `yfinance` Python package directly.
- **Use:**

```bash
python scripts/ingest_historical.py --source yfinance --symbols AAPL --interval 1d
```

If `yfinance` is blocked, switch to `alpha_vantage` or `multi_source`.

---

## 4. Web scraper (no-key fallback)

- Direct HTTP scrape of Yahoo Finance / Stooq pages - no key required.
- Limited throughput and brittle to layout changes.  Use only as last resort.
- **Use:**

```bash
python scripts/ingest_historical.py --source web_scraper --symbols AAPL --interval 1d
```

---

## 5. Multi-source (default in `.env`)

Automatic failover chain - tries each provider in order until one returns
non-empty data.  Chains are configured per interval in
`backend/app/data_sources/multi_source.py`.

```python
DEFAULT_CHAINS = {
    "1d":  ["yfinance", "finnhub", "yfinance_direct", "alpha_vantage"],
    "1h":  ["yfinance", "yfinance_direct", "finnhub"],
    "15m": ["yfinance", "yfinance_direct", "finnhub"],
    "5m":  ["yfinance", "yfinance_direct"],
}
```

**Use:**

```bash
python scripts/ingest_historical.py --source multi_source --symbols AAPL --interval 1d
```

If yfinance is blocked and Finnhub key is invalid, the chain silently falls
through to Alpha Vantage and still returns data.

---

## Switching sources

The active source is controlled by the `DATA_SOURCE` variable in `.env`:

```env
DATA_SOURCE=multi_source   # default
DATA_SOURCE=alpha_vantage
DATA_SOURCE=finnhub
DATA_SOURCE=yfinance
DATA_SOURCE=web_scraper
```

Or override per-run with `--source`:

```bash
python scripts/ingest_historical.py --source alpha_vantage --symbols AAPL --interval 1d
```

---

## Recommended setup for KLTN

For a free, reliable historical data pipeline:

```env
DATA_SOURCE=multi_source
ALPHA_VANTAGE_API_KEY=<your-free-key>     # primary on free tier
FINNHUB_API_KEY=<your-free-key>           # secondary (60 req/min)
# yfinance needs no key but is rate-limited
```

With `multi_source`, the pipeline always finds a working provider.
