$base = "http://127.0.0.1:8000/api/v1"

function Quick-Test {
    param($name, $method, $url, $body = $null, $timeout = 8)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $params = @{ Uri = $url; Method = $method; UseBasicParsing = $true; TimeoutSec = $timeout }
        if ($body) { $params.Body = ($body | ConvertTo-Json -Depth 5); $params.ContentType = "application/json" }
        $r = Invoke-WebRequest @params -ErrorAction Stop
        $sw.Stop()
        Write-Host ("[OK ] {0,-50} {1} {2} ({3}ms, {4}B)" -f $name, $method, $r.StatusCode, $sw.ElapsedMilliseconds, $r.Content.Length)
    } catch {
        $sw.Stop()
        $code = $_.Exception.Response.StatusCode.value__
        if (-not $code) { $code = "ERR" }
        $note = $_.Exception.Message
        try {
            $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $note = $sr.ReadToEnd().Substring(0, [Math]::Min(100, $sr.ReadToEnd().Length))
        } catch {}
        Write-Host ("[FAIL] {0,-50} {1} {2} ({3}ms) {4}" -f $name, $method, $code, $sw.ElapsedMilliseconds, $note) -ForegroundColor Red
    }
}

Write-Host "===== BACKTESTS =====" -ForegroundColor Cyan
Quick-Test "backtests.history" GET "$base/backtests/history?limit=3"
Quick-Test "backtests.run (GET no body)" GET "$base/backtests/run"

Write-Host "`n===== FORECAST =====" -ForegroundColor Cyan
Quick-Test "forecast.compare.AAPL" GET "$base/forecast/compare/AAPL"
Quick-Test "forecast.predict (no body)" GET "$base/forecast/predict"
Quick-Test "forecast.train (no body)" GET "$base/forecast/train"

Write-Host "`n===== AGENT =====" -ForegroundColor Cyan
Quick-Test "agent.history.test123" GET "$base/agent/history/test123"
$agentBody = @{ message = "Xin chào"; session_id = "smoke-test-1" }
Quick-Test "agent.chat" POST "$base/agent/chat" $agentBody 30

Write-Host "`n===== STREAM =====" -ForegroundColor Cyan
Quick-Test "stream.ingest" POST "$base/stream/ingest" @{ symbol = "AAPL"; price = 100.5; volume = 1000 }
Quick-Test "stream.stats" GET "$base/stream/stats"

Write-Host "`n===== ADMIN =====" -ForegroundColor Cyan
Quick-Test "admin.auto-refresh.status" GET "$base/admin/auto-refresh/status"

Write-Host "`n===== INGEST (data update) =====" -ForegroundColor Cyan
Quick-Test "data.stocks.ingest (no body)" GET "$base/data/stocks/ingest"
Quick-Test "data.fundamental.ingest" GET "$base/data/fundamental/ingest"
Quick-Test "data.macro.ingest" GET "$base/data/macro/ingest"
Quick-Test "data.news.ingest" GET "$base/data/news/ingest"

Write-Host "`n===== DASHBOARD specific symbol =====" -ForegroundColor Cyan
Quick-Test "dashboard.MSFT" GET "$base/dashboard/MSFT"
Quick-Test "dashboard.NVDA" GET "$base/dashboard/NVDA"

Write-Host "`nDONE" -ForegroundColor Green
