# Vietnam Real-time Streaming (SSI iBoard WebSocket)

> Free, no API key, no registration — HOSE / HNX / UPCOM real-time quotes
> delivered straight into the lakehouse the same way the website
> `iboard.ssi.com.vn` consumes them.

## Overview

This module streams real-time stock prices for **Vietnamese** tickers
into the same Kafka pipeline used by the US provider (Finnhub).
Both publishers write to topic `stock-ohlcv-raw` and are
indistinguishable from the lakehouse's perspective except for the
`source` column on each bar:

| Source tag  | Path        | Latency      | Active during             |
|-------------|-------------|--------------|---------------------------|
| `finnhub_ws`  | Finnhub WebSocket | sub-second | US market hours  |
| `finnhub_rest`| Finnhub REST      | ≤ 15 min   | US off-hours, weekends |
| `vn_ws`       | SSI iBoard WS     | sub-second | VN market hours  |
| `vn_rest`     | SSI iBoard REST   | 1 min      | VN off-hours, weekends |

The frontend's SSE stream (`/api/v1/stream/events?symbol=FPT`) picks
bars from any of the four sources transparently.

## Endpoint

`wss://iboard-pushstream.ssi.com.vn/realtime`

- **Public**, anonymous — no token, no consumer secret, no captcha.
- Same endpoint the website `iboard.ssi.com.vn` uses to push quotes
  into the browser.

## Protocol

A *GraphQL-over-WebSocket* subscription. The client sends a single
JSON subscribe message after `onopen`:

```json
{
  "type": "sub",
  "topic": "stockRealtimeBySymbolsAndBoards",
  "variables": {
    "symbols": ["FPT", "VNM"],
    "boardIds": ["MAIN"]
  },
  "component": "priceTableEquities"
}
```

The server pushes two shapes of data:

- **Quote tick** — a single `|`-delimited string of ~70 numeric fields.
  Field offsets are documented inline in
  [`vn_websocket.py`](../app/streaming/vn_websocket.py) and reverse-engineered
  from `vnstock-js@1.5.1` (see "Source of truth" below).
  **All monetary values are reported in *thousand VND* and must be
  divided by 1000 to obtain absolute VND.**

- **Control / error** — a JSON object containing an `error` key.

There is **no client-side ping/pong**. The client uses a dead-man
timer (default 60s) to detect a stuck connection; when no message
arrives within the timeout, the socket is closed and the reconnect
loop kicks in.

## Trading hours

| Exchange | Morning  | Afternoon | Days      |
|----------|----------|-----------|-----------|
| HOSE     | 09:00 - 11:30 ICT | 13:00 - 15:00 ICT | Mon - Fri |
| HNX      | 09:00 - 11:30 ICT | 13:00 - 15:00 ICT | Mon - Fri |
| UPCOM    | 09:00 - 11:30 ICT | 13:00 - 15:00 ICT | Mon - Fri |

Outside those hours the WebSocket stays open but no ticks are pushed.
The REST poller (`VNRestPoller`) keeps the lakehouse fed with the most
recent daily/1-minute candle, deduplicated by timestamp.

## Configuration

All knobs are read from `app.core.config.Settings`. Defaults below
match `.env.example`.

| Env var                  | Default                                            | Meaning                              |
|--------------------------|----------------------------------------------------|--------------------------------------|
| `VN_WS_SYMBOLS`          | `FPT,VNM,VCB,HPG,MWG,VIC,VHM,MSN,BID,CTG`          | Comma-separated VN tickers to subscribe |
| `VN_WS_BOARDS`           | `MAIN,HNX,UPCOM`                                   | Board filter (MAIN = HOSE)          |
| `VN_WS_DEAD_MAN_SECONDS` | `60`                                               | Force reconnect after N s of silence |
| `VN_WS_ENABLED`          | `true`                                             | Master switch                       |
| `DATA_SOURCE`            | (unchanged)                                        | Set to `vn_ws` to use SSI as the default historical provider |

## Running

### Via Docker (recommended)

`docker-compose.yml` ships a `vn-stream-publisher` service that runs
the publisher in a container alongside the rest of the stack. Start
it with:

```bash
docker compose --profile app up -d vn-stream-publisher
```

To enable both US + VN publishers simultaneously, just include both
services in the same `up` call:

```bash
docker compose --profile app up -d stream-publisher vn-stream-publisher
```

The `stream-publisher` (US) and `vn-stream-publisher` (VN) write to the
same `stock-ohlcv-raw` topic; the `source` column tells them apart.

### Standalone (for debugging)

```bash
cd backend
python -m app.streaming.vn_stream_publisher \
    --symbols FPT,VNM \
    --boards MAIN,HNX,UPCOM \
    --bootstrap localhost:9094 \
    --duration 120
```

Or the low-level client directly:

```bash
python -m app.streaming.vn_websocket \
    --symbols FPT,VNM \
    --boards MAIN \
    --duration 30
```

This prints each tick to stdout and exits after 30 s.

## Verifying

1. **Container logs**
   ```bash
   docker compose logs -f vn-stream-publisher
   ```
   You should see lines like
   `VNStreamPublisher started: symbols=10 topic=stock-ohlcv-raw broker=kafka:9092 ...`
   followed by per-minute `VNStreamPublisher published N fresh bar(s) ...`
   during trading hours.

2. **Kafka topic**
   ```bash
   docker exec -it stock-lakehouse-kafka \
       /opt/kafka/bin/kafka-console-consumer.sh \
       --bootstrap-server localhost:9092 \
       --topic stock-ohlcv-raw --from-beginning \
       | grep vn_ws
   ```
   You should see JSON envelopes of the form
   `{"symbol":"FPT","bars":[{...,"source":"vn_ws",...}]}`.

3. **SSE stream from the API**
   ```bash
   curl -N "http://localhost:8000/api/v1/stream/events?symbol=FPT"
   ```
   During trading hours, you should see `event: bar` frames roughly
   once per minute with the latest 1-minute bar.

4. **Bronze / Silver**
   The `StockKafkaConsumer` (in `app.streaming.kafka_consumer`) reads
   the same topic and writes to Bronze + Silver; a simple Parquet
   query confirms the data is there:
   ```python
   import pandas as pd
   df = pd.read_parquet("data/silver/stock_prices/year=2026/month=10")
   print(df[df["source"] == "vn_ws"].tail())
   ```

## Known limitations

- **No level-3 order book** — iBoard pushstream exposes top-3 bid/ask
  only. For deeper order-book data a paid `SSI FastConnect` consumer
  key is required.
- **No OHLC per bar in the stream** — the tick carries only the last
  matched price. The 1-minute OHLCV bar is assembled client-side by
  `VNStreamPublisher` from all ticks received during the minute.
- **Outage risk** — SSI's public endpoint has had multi-hour outages
  during VN trading hours in the past (May 2026). The dead-man
  timer + exponential backoff + REST poller mitigate this, but the
  lakehouse WILL go silent during an SSI outage.
- **Symbol universe** — only tickers listed on HOSE / HNX / UPCOM
  with iBoard coverage. Penny stocks and delisted tickers may not
  be in the stream.

## Source of truth

The field offsets and subscribe JSON shape were reverse-engineered
from `vnstock-js@1.5.1` (the same library that powers
`vnstock`'s real-time class):

- Decompiled JS:
  <https://cdn.jsdelivr.net/npm/vnstock-js@1.5.1/dist/realtime/index.js>
- Library docs: <https://vnstock-js-docs.vercel.app/docs/key-features/advanced/realtime>
- Companion reverse-engineering notes:
  <https://github.com/Kohnnn/vnibb/blob/main/apps/api/docs/ssi_iboard_documentation.md>

## Cost

**$0.** The endpoint is public and there is no published rate limit
beyond the implicit fairness shared with the website. The REST
poller is also free.
