$base = "http://127.0.0.1:8000/api/v1"
$results = @()

function Test-Endpoint {
    param($name, $method, $url, $body = $null, $timeout = 10)
    $start = Get-Date
    try {
        $params = @{
            Uri = $url
            Method = $method
            UseBasicParsing = $true
            TimeoutSec = $timeout
            ContentType = "application/json"
        }
        if ($body) { $params.Body = ($body | ConvertTo-Json -Depth 5) }
        $r = Invoke-WebRequest @params -ErrorAction Stop
        $ms = ((Get-Date) - $start).TotalMilliseconds
        $code = $r.StatusCode
        $len = $r.Content.Length
        return [PSCustomObject]@{
            Name = $name
            Method = $method
            URL = $url
            Code = $code
            Ms = [int]$ms
            Len = $len
            OK = ($code -ge 200 -and $code -lt 400)
        }
    } catch {
        $ms = ((Get-Date) - $start).TotalMilliseconds
        $code = $_.Exception.Response.StatusCode.value__
        $body_ = $null
        try { $body_ = ($_.Exception.Response).GetResponseStream() | ForEach-Object { (New-Object System.IO.StreamReader($_)).ReadToEnd() } } catch {}
        return [PSCustomObject]@{
            Name = $name
            Method = $method
            URL = $url
            Code = if ($code) { $code } else { "ERR" }
            Ms = [int]$ms
            Len = if ($body_) { $body_.Length } else { 0 }
            OK = $false
            Note = if ($body_) { $body_.Substring(0, [Math]::Min(200, $body_.Length)) } else { $_.Exception.Message }
        }
    }
}

# Batch 1: System + health + data layer
$results += Test-Endpoint "health" GET "$base/health"
$results += Test-Endpoint "system.status" GET "$base/system/status"
$results += Test-Endpoint "pipeline.storage.status" GET "$base/pipeline/storage/status"
$results += Test-Endpoint "pipeline.symbols.supported" GET "$base/pipeline/symbols/supported"
$results += Test-Endpoint "stocks.symbols" GET "$base/stocks/symbols"

# Batch 2: Stocks data (use AAPL as test)
$results += Test-Endpoint "stocks.AAPL" GET "$base/stocks/AAPL?limit=5"
$results += Test-Endpoint "stocks.AAPL.latest" GET "$base/stocks/AAPL/latest"
$results += Test-Endpoint "stocks.AAPL.csv" GET "$base/stocks/AAPL/csv?limit=5"
$results += Test-Endpoint "stocks.AAPL.indicators" GET "$base/stocks/AAPL/indicators?limit=5"
$results += Test-Endpoint "data.stocks.AAPL" GET "$base/data/stocks/AAPL?limit=5"
$results += Test-Endpoint "data.stocks.AAPL.latest" GET "$base/data/stocks/AAPL/latest"
$results += Test-Endpoint "data.stocks.supported" GET "$base/data/stocks/supported"

# Batch 3: Pipeline
$results += Test-Endpoint "pipeline.layers.AAPL" GET "$base/pipeline/layers/AAPL"
$results += Test-Endpoint "pipeline.data.AAPL" GET "$base/pipeline/data/AAPL?layer=gold&limit=5"
$results += Test-Endpoint "dashboard.AAPL" GET "$base/dashboard/AAPL"

# Batch 4: Macro + market
$results += Test-Endpoint "macro.summary" GET "$base/data/macro/summary"
$results += Test-Endpoint "macro.cpi" GET "$base/data/macro/cpi"
$results += Test-Endpoint "macro.exchange-rate" GET "$base/data/macro/exchange-rate"
$results += Test-Endpoint "macro.gold" GET "$base/data/macro/gold"
$results += Test-Endpoint "macro.oil" GET "$base/data/macro/oil"
$results += Test-Endpoint "macro.interest-rates" GET "$base/data/macro/interest-rates"

# Batch 5: Market indices
$results += Test-Endpoint "market.indices" GET "$base/market/indices"
$results += Test-Endpoint "market.indices.sectors" GET "$base/market/indices/sectors"

# Batch 6: News + sentiment
$results += Test-Endpoint "data.news.market" GET "$base/data/news/market?limit=5"
$results += Test-Endpoint "data.news.AAPL" GET "$base/data/news/AAPL?limit=5"
$results += Test-Endpoint "data.sentiment.AAPL" GET "$base/data/sentiment/AAPL"
$results += Test-Endpoint "market.news.market" GET "$base/market/news/market?limit=5"
$results += Test-Endpoint "market.news.AAPL" GET "$base/market/news/AAPL?limit=5"
$results += Test-Endpoint "market.news.AAPL.sentiment-summary" GET "$base/market/news/AAPL/sentiment-summary"
$results += Test-Endpoint "market.news.AAPL.sentiment-timeseries" GET "$base/market/news/AAPL/sentiment-timeseries"

# Batch 7: Fundamental
$results += Test-Endpoint "data.fundamental.AAPL" GET "$base/data/fundamental/AAPL"
$results += Test-Endpoint "market.fundamental.AAPL" GET "$base/market/fundamental/AAPL"
$results += Test-Endpoint "market.fundamental.AAPL.balance-sheet" GET "$base/market/fundamental/AAPL/balance-sheet"
$results += Test-Endpoint "market.fundamental.AAPL.cash-flow" GET "$base/market/fundamental/AAPL/cash-flow"
$results += Test-Endpoint "market.fundamental.AAPL.income-statement" GET "$base/market/fundamental/AAPL/income-statement"

# Batch 8: Orderbook / trades (likely 404 if no live feed)
$results += Test-Endpoint "market.orderbook.AAPL" GET "$base/market/orderbook/AAPL"
$results += Test-Endpoint "market.trades.AAPL" GET "$base/market/trades/AAPL?limit=5"
$results += Test-Endpoint "market.trades.AAPL.summary" GET "$base/market/trades/AAPL/summary"

# Batch 9: Streaming
$results += Test-Endpoint "stream.latest" GET "$base/stream/latest"
$results += Test-Endpoint "stream.history" GET "$base/stream/history?limit=5"
$results += Test-Endpoint "stream.events" GET "$base/stream/events?limit=5"
$results += Test-Endpoint "stream.stats" GET "$base/stream/stats"

# Batch 10: Forecast + backtest
$results += Test-Endpoint "forecast.compare.AAPL" GET "$base/forecast/compare/AAPL"
$results += Test-Endpoint "backtests.history" GET "$base/backtests/history?limit=5"

# Batch 11: Admin
$results += Test-Endpoint "admin.auto-refresh.status" GET "$base/admin/auto-refresh/status"

# Print summary
$results | Format-Table Name, Method, Code, Ms, OK, Len -AutoSize
Write-Host "===== SUMMARY =====" -ForegroundColor Cyan
$total = $results.Count
$ok = ($results | Where-Object { $_.OK }).Count
$fail = $total - $ok
Write-Host "Total: $total | OK: $ok | Fail: $fail" -ForegroundColor Yellow
if ($fail -gt 0) {
    Write-Host "`n===== FAILURES =====" -ForegroundColor Red
    $results | Where-Object { -not $_.OK } | Format-Table Name, Method, Code, Note -AutoSize
}
