$base = "http://127.0.0.1:8000/api/v1"

function Quick-Test {
    param($name, $method, $url, $body = $null, $timeout = 5)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $params = @{
            Uri = $url; Method = $method; UseBasicParsing = $true
            TimeoutSec = $timeout
        }
        if ($body) { $params.Body = ($body | ConvertTo-Json -Depth 5); $params.ContentType = "application/json" }
        $r = Invoke-WebRequest @params -ErrorAction Stop
        $sw.Stop()
        $code = $r.StatusCode
        Write-Host ("[OK ] {0,-50} {1} {2} ({3}ms, {4}B)" -f $name, $method, $code, $sw.ElapsedMilliseconds, $r.Content.Length)
    } catch {
        $sw.Stop()
        $code = $_.Exception.Response.StatusCode.value__
        if (-not $code) { $code = "ERR" }
        $note = $_.Exception.Message
        if ($_.Exception.Response) {
            try {
                $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $note = $sr.ReadToEnd().Substring(0, [Math]::Min(120, $sr.ReadToEnd().Length))
            } catch {}
        }
        Write-Host ("[FAIL] {0,-50} {1} {2} ({3}ms) {4}" -f $name, $method, $code, $sw.ElapsedMilliseconds, $note) -ForegroundColor Red
    }
}

Write-Host "===== BATCH 1: System / pipeline / storage =====" -ForegroundColor Cyan
Quick-Test "health" GET "$base/health"
Quick-Test "system.status" GET "$base/system/status"
Quick-Test "pipeline.storage.status" GET "$base/pipeline/storage/status"
Quick-Test "pipeline.symbols.supported" GET "$base/pipeline/symbols/supported"
Quick-Test "stocks.symbols" GET "$base/stocks/symbols"

Write-Host "`n===== BATCH 2: Stocks data =====" -ForegroundColor Cyan
Quick-Test "stocks.AAPL" GET "$base/stocks/AAPL?limit=3"
Quick-Test "stocks.AAPL.latest" GET "$base/stocks/AAPL/latest"
Quick-Test "stocks.AAPL.csv" GET "$base/stocks/AAPL/csv?limit=3"
Quick-Test "stocks.AAPL.indicators" GET "$base/stocks/AAPL/indicators?limit=3"
Quick-Test "data.stocks.AAPL" GET "$base/data/stocks/AAPL?limit=3"
Quick-Test "data.stocks.AAPL.latest" GET "$base/data/stocks/AAPL/latest"
Quick-Test "data.stocks.supported" GET "$base/data/stocks/supported"

Write-Host "`n===== BATCH 3: Pipeline / dashboard =====" -ForegroundColor Cyan
Quick-Test "pipeline.layers.AAPL" GET "$base/pipeline/layers/AAPL"
Quick-Test "pipeline.data.AAPL" GET "$base/pipeline/data/AAPL?layer=gold&limit=3"
Quick-Test "dashboard.AAPL" GET "$base/dashboard/AAPL"

Write-Host "`n===== BATCH 4: Macro =====" -ForegroundColor Cyan
Quick-Test "macro.summary" GET "$base/data/macro/summary"
Quick-Test "macro.cpi" GET "$base/data/macro/cpi"
Quick-Test "macro.exchange-rate" GET "$base/data/macro/exchange-rate"
Quick-Test "macro.gold" GET "$base/data/macro/gold"
Quick-Test "macro.oil" GET "$base/data/macro/oil"
Quick-Test "macro.interest-rates" GET "$base/data/macro/interest-rates"

Write-Host "`n===== BATCH 5: Market indices =====" -ForegroundColor Cyan
Quick-Test "market.indices" GET "$base/market/indices"
Quick-Test "market.indices.sectors" GET "$base/market/indices/sectors"

Write-Host "`n===== BATCH 6: News / sentiment =====" -ForegroundColor Cyan
Quick-Test "data.news.market" GET "$base/data/news/market?limit=3"
Quick-Test "data.news.AAPL" GET "$base/data/news/AAPL?limit=3"
Quick-Test "data.sentiment.AAPL" GET "$base/data/sentiment/AAPL"
Quick-Test "market.news.market" GET "$base/market/news/market?limit=3"
Quick-Test "market.news.AAPL" GET "$base/market/news/AAPL?limit=3"
Quick-Test "market.news.AAPL.sentiment-summary" GET "$base/market/news/AAPL/sentiment-summary"
Quick-Test "market.news.AAPL.sentiment-timeseries" GET "$base/market/news/AAPL/sentiment-timeseries"

Write-Host "`n===== BATCH 7: Fundamental =====" -ForegroundColor Cyan
Quick-Test "data.fundamental.AAPL" GET "$base/data/fundamental/AAPL"
Quick-Test "market.fundamental.AAPL" GET "$base/market/fundamental/AAPL"
Quick-Test "market.fundamental.AAPL.balance-sheet" GET "$base/market/fundamental/AAPL/balance-sheet"
Quick-Test "market.fundamental.AAPL.cash-flow" GET "$base/market/fundamental/AAPL/cash-flow"
Quick-Test "market.fundamental.AAPL.income-statement" GET "$base/market/fundamental/AAPL/income-statement"

Write-Host "`n===== BATCH 8: Orderbook / trades (live) =====" -ForegroundColor Cyan
Quick-Test "market.orderbook.AAPL" GET "$base/market/orderbook/AAPL"
Quick-Test "market.trades.AAPL" GET "$base/market/trades/AAPL?limit=3"
Quick-Test "market.trades.AAPL.summary" GET "$base/market/trades/AAPL/summary"

Write-Host "`n===== BATCH 9: Streaming =====" -ForegroundColor Cyan
Quick-Test "stream.latest" GET "$base/stream/latest"
Quick-Test "stream.history" GET "$base/stream/history?limit=3"
Quick-Test "stream.events" GET "$base/stream/events?limit=3"
Quick-Test "stream.stats" GET "$base/stream/stats"

Write-Host "`n===== BATCH 10: Forecast / backtest / admin =====" -ForegroundColor Cyan
Quick-Test "forecast.compare.AAPL" GET "$base/forecast/compare/AAPL"
Quick-Test "backtests.history" GET "$base/backtests/history?limit=3"
Quick-Test "admin.auto-refresh.status" GET "$base/admin/auto-refresh/status"

Write-Host "`n===== DONE =====" -ForegroundColor Green
