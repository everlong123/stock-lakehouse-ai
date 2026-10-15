$base = "http://127.0.0.1:8000/api/v1"

function Get-Error {
    param($url, $timeout = 5)
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $timeout -ErrorAction Stop
        return "200: $($r.Content.Substring(0, [Math]::Min(200, $r.Content.Length)))"
    } catch {
        $resp = $_.Exception.Response
        $code = $resp.StatusCode.value__
        $body = ""
        if ($resp) {
            try {
                $stream = $resp.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream)
                $body = $reader.ReadToEnd()
            } catch {}
        }
        return "$code : $body"
    }
}

$cases = @(
    "http://127.0.0.1:8000/api/v1/stocks/AAPL?limit=3",
    "http://127.0.0.1:8000/api/v1/pipeline/data/AAPL?layer=gold&limit=3",
    "http://127.0.0.1:8000/api/v1/dashboard/AAPL",
    "http://127.0.0.1:8000/api/v1/market/indices",
    "http://127.0.0.1:8000/api/v1/data/fundamental/AAPL",
    "http://127.0.0.1:8000/api/v1/stream/history?limit=3"
)

foreach ($u in $cases) {
    Write-Host "`n--- $u ---" -ForegroundColor Yellow
    Get-Error $u 6
}
