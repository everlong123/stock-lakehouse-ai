$base = "http://127.0.0.1:8000/api/v1"
$ok = 0; $fail = 0; $results = @()

function Quick-Test {
    param($name, $method, $url, $body = $null, $timeout = 8, $expect = @(200, 201, 204))
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $params = @{ Uri = $url; Method = $method; UseBasicParsing = $true; TimeoutSec = $timeout }
        if ($body) { $params.Body = ($body | ConvertTo-Json -Depth 5); $params.ContentType = "application/json" }
        $r = Invoke-WebRequest @params -ErrorAction Stop
        $sw.Stop()
        $code = $r.StatusCode
        $isOk = $expect -contains $code
        $script:ok += if ($isOk) { 1 } else { 0 }
        $script:fail += if ($isOk) { 0 } else { 1 }
        return [PSCustomObject]@{ Name = $name; Method = $method; URL = $url; Code = $code; OK = $isOk; Ms = $sw.ElapsedMilliseconds; Note = "" }
    } catch {
        $sw.Stop()
        $code = $_.Exception.Response.StatusCode.value__
        if (-not $code) { $code = "ERR" }
        # 405 method not allowed = wrong test setup (endpoint exists)
        $isOk = $expect -contains $code
        $script:ok += if ($isOk) { 1 } else { 0 }
        $script:fail += if ($isOk) { 0 } else { 1 }
        $note = ""
        try { $note = (New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } catch {}
        return [PSCustomObject]@{ Name = $name; Method = $method; URL = $url; Code = $code; OK = $isOk; Ms = $sw.ElapsedMilliseconds; Note = $note.Substring(0, [Math]::Min(80, $note.Length)) }
    }
}

# Test all key endpoints with proper params
$tests = @(
    @{ n = "health"; m = "GET"; u = "$base/health" }
    @{ n = "system.status"; m = "GET"; u = "$base/system/status" }
    @{ n = "pipeline.storage.status"; m = "GET"; u = "$base/pipeline/storage/status" }
    @{ n = "pipeline.symbols.supported"; m = "GET"; u = "$base/pipeline/symbols/supported" }
    @{ n = "stocks.symbols"; m = "GET"; u = "$base/stocks/symbols" }
    @{ n = "stocks.AAPL"; m = "GET"; u = "$base/stocks/AAPL" }
    @{ n = "stocks.AAPL.latest"; m = "GET"; u = "$base/stocks/AAPL/latest" }
    @{ n = "stocks.AAPL.csv"; m = "GET"; u = "$base/stocks/AAPL/csv?limit=10" }
    @{ n = "stocks.AAPL.indicators"; m = "GET"; u = "$base/stocks/AAPL/indicators?limit=10" }
    @{ n = "data.stocks.AAPL"; m = "GET"; u = "$base/data/stocks/AAPL?limit=5" }
    @{ n = "data.stocks.AAPL.latest"; m = "GET"; u = "$base/data/stocks/AAPL/latest" }
    @{ n = "data.stocks.supported"; m = "GET"; u = "$base/data/stocks/supported" }
    @{ n = "pipeline.layers.AAPL"; m = "GET"; u = "$base/pipeline/layers/AAPL" }
    @{ n = "pipeline.data.AAPL"; m = "GET"; u = "$base/pipeline/data/AAPL?layer=gold&limit=5" }
    @{ n = "dashboard.AAPL"; m = "GET"; u = "$base/dashboard/AAPL" }
    @{ n = "macro.cpi"; m = "GET"; u = "$base/data/macro/cpi" }
    @{ n = "macro.gold"; m = "GET"; u = "$base/data/macro/gold" }
    @{ n = "macro.oil"; m = "GET"; u = "$base/data/macro/oil" }
    @{ n = "macro.exchange-rate"; m = "GET"; u = "$base/data/macro/exchange-rate"; t = 25 }
    @{ n = "macro.interest-rates"; m = "GET"; u = "$base/data/macro/interest-rates"; t = 25 }
    @{ n = "macro.summary"; m = "GET"; u = "$base/data/macro/summary"; t = 30 }
    @{ n = "market.indices"; m = "GET"; u = "$base/market/indices" }
    @{ n = "market.indices.sectors"; m = "GET"; u = "$base/market/indices/sectors" }
    @{ n = "data.news.market"; m = "GET"; u = "$base/data/news/market?limit=3" }
    @{ n = "data.news.AAPL"; m = "GET"; u = "$base/data/news/AAPL?limit=3" }
    @{ n = "data.sentiment.AAPL"; m = "GET"; u = "$base/data/sentiment/AAPL" }
    @{ n = "market.news.market"; m = "GET"; u = "$base/market/news/market?limit=3" }
    @{ n = "market.news.AAPL"; m = "GET"; u = "$base/market/news/AAPL?limit=3" }
    @{ n = "market.news.AAPL.sentiment-summary"; m = "GET"; u = "$base/market/news/AAPL/sentiment-summary" }
    @{ n = "market.news.AAPL.sentiment-timeseries"; m = "GET"; u = "$base/market/news/AAPL/sentiment-timeseries" }
    @{ n = "data.fundamental.AAPL"; m = "GET"; u = "$base/data/fundamental/AAPL" }
    @{ n = "market.fundamental.AAPL"; m = "GET"; u = "$base/market/fundamental/AAPL" }
    @{ n = "market.fundamental.AAPL.balance-sheet"; m = "GET"; u = "$base/market/fundamental/AAPL/balance-sheet" }
    @{ n = "market.fundamental.AAPL.cash-flow"; m = "GET"; u = "$base/market/fundamental/AAPL/cash-flow" }
    @{ n = "market.fundamental.AAPL.income-statement"; m = "GET"; u = "$base/market/fundamental/AAPL/income-statement" }
    @{ n = "market.orderbook.AAPL"; m = "GET"; u = "$base/market/orderbook/AAPL" }
    @{ n = "market.trades.AAPL"; m = "GET"; u = "$base/market/trades/AAPL?limit=3" }
    @{ n = "market.trades.AAPL.summary"; m = "GET"; u = "$base/market/trades/AAPL/summary" }
    @{ n = "stream.latest"; m = "GET"; u = "$base/stream/latest" }
    @{ n = "stream.stats"; m = "GET"; u = "$base/stream/stats" }
    @{ n = "stream.history.AAPL"; m = "GET"; u = "$base/stream/history?symbol=AAPL&limit=3" }
    @{ n = "stream.events"; m = "GET"; u = "$base/stream/events?limit=3" }
    @{ n = "backtests.history"; m = "GET"; u = "$base/backtests/history?limit=3" }
    @{ n = "forecast.compare.AAPL"; m = "GET"; u = "$base/forecast/compare/AAPL" }
    @{ n = "agent.history.test"; m = "GET"; u = "$base/agent/history/test-session" }
    @{ n = "admin.auto-refresh.status"; m = "GET"; u = "$base/admin/auto-refresh/status" }
    @{ n = "data.news.ingest"; m = "GET"; u = "$base/data/news/ingest"; t = 15 }
)

foreach ($t in $tests) {
    $timeout = if ($t.t) { $t.t } else { 8 }
    $results += Quick-Test -name $t.n -method $t.m -url $t.u -timeout $timeout
}

$results | Format-Table Name, Code, OK, Ms -AutoSize
Write-Host "`n========== SUMMARY ==========" -ForegroundColor Cyan
Write-Host "Total: $($results.Count)" -ForegroundColor Yellow
Write-Host "OK: $ok" -ForegroundColor Green
Write-Host "Fail: $fail" -ForegroundColor Red
$failed = $results | Where-Object { -not $_.OK }
if ($failed) {
    Write-Host "`n========== FAILURES ==========" -ForegroundColor Red
    $failed | Format-Table Name, Code, Note -AutoSize
}
