# start-all.ps1
# Khởi động toàn bộ dev stack LOCAL:
#   - Backend  (FastAPI :8000) trong cửa sổ cmd "Stock-LH-Backend"
#   - Frontend (Vite    :5173) trong cửa sổ cmd "Stock-LH-Frontend"
#
# Mỗi service chạy trong cửa sổ cmd RIÊNG (đóng cửa sổ = tắt service đó).
# Launcher chỉ chờ ports mở rồi thoát; 2 cửa sổ service vẫn chạy độc lập.
#
# CÁCH DÙNG:
#   cd D:\School\kltn\stock-lakehouse-ai
#   powershell -ExecutionPolicy Bypass -File .\start-all.ps1
# Hoặc double-click start-all.bat
#
# Sau khi chạy, mở trình duyệt: http://127.0.0.1:5173
# Tắt: .\stop-all.ps1  (hoặc đóng 2 cửa sổ cmd).

$ErrorActionPreference = "Continue"
$root      = $PSScriptRoot
$backend   = Join-Path $root "backend"
$frontend  = Join-Path $root "frontend"
$venvPy    = Join-Path $backend  ".venv\Scripts\python.exe"
$backendPort  = 8000
$frontendPort = 5173

function Stop-Existing {
    Write-Host "[stop] Killing leftover uvicorn / vite processes..." -ForegroundColor Yellow
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.CommandLine -like '*uvicorn app.main*'
    } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue } catch {} }
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object {
        $_.CommandLine -match 'vite' -and $_.CommandLine -notmatch 'Cursor'
    } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue } catch {} }
    Start-Sleep -Seconds 1
}

function Wait-Port {
    param([int]$Port, [string]$Name, [int]$TimeoutSec = 30)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(500, $false)
            $client.Close()
            if ($ok) {
                Write-Host "  [OK] $Name listening on :$Port ($([int]$sw.Elapsed.TotalSeconds)s)" -ForegroundColor Green
                return $true
            }
        } catch { try { $client.Close() } catch {} }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "  [WARN] $Name did not start within ${TimeoutSec}s" -ForegroundColor Red
    return $false
}

function Start-Window {
    param(
        [string]$Title,
        [string]$Command
    )
    # We want a NEW cmd window that:
    #   1. has a fixed title (so the user can find it)
    #   2. runs the launch command
    #   3. stays open after the command exits (so the user can see errors)
    # The reliable way on Windows is: Start-Process cmd.exe with /K (keep open)
    # and let it run the entire command string. The outer Start-Process returns
    # immediately because the process is detached.
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/D", "/K", "title $Title && $Command" `
        -WindowStyle Normal
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Stock Lakehouse AI - Dev Stack Launcher  " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Backend:  http://127.0.0.1:$backendPort"      -ForegroundColor Gray
Write-Host "  Frontend: http://127.0.0.1:$frontendPort"     -ForegroundColor Gray
Write-Host "  Agent UI: http://127.0.0.1:$frontendPort/agent" -ForegroundColor Gray
Write-Host ""

if (-not (Test-Path $venvPy)) {
    Write-Host "[ERROR] Backend venv not found: $venvPy" -ForegroundColor Red
    Write-Host "        Create it first: cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "[WARN] frontend/node_modules missing. Run 'npm install' in frontend/ first." -ForegroundColor Yellow
}

Stop-Existing

# ---- Start backend in its own persistent cmd window ----
Write-Host "[1/2] Starting backend (uvicorn on :$backendPort)..." -ForegroundColor Cyan
$backendCmd = "cd /d `"$backend`" && title Stock-LH Backend :$backendPort && `"$venvPy`" -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort"
Start-Window -Title "Stock-LH-Backend" -Command $backendCmd

# ---- Start frontend in its own persistent cmd window ----
Write-Host "[2/2] Starting frontend (vite on :$frontendPort)..." -ForegroundColor Cyan
$frontendCmd = "cd /d `"$frontend`" && title Stock-LH Frontend :$frontendPort && npm run dev"
Start-Window -Title "Stock-LH-Frontend" -Command $frontendCmd

Write-Host ""
Write-Host "[wait] Waiting for services to come up..." -ForegroundColor Yellow
$backendUp  = Wait-Port -Port $backendPort  -Name "Backend"  -TimeoutSec 30
$frontendUp = Wait-Port -Port $frontendPort -Name "Frontend" -TimeoutSec 45

Write-Host ""
if ($backendUp -and $frontendUp) {
    Write-Host "All services are up." -ForegroundColor Green
    Write-Host "  - Open http://127.0.0.1:$frontendPort in your browser" -ForegroundColor Green
    Write-Host "  - Stop: run .\stop-all.ps1  (or close the 2 cmd windows)" -ForegroundColor Green
} else {
    Write-Host "Some services failed to start. Check the cmd windows for errors." -ForegroundColor Red
    Write-Host "  - Backend window:  Stock-LH-Backend"  -ForegroundColor Gray
    Write-Host "  - Frontend window: Stock-LH-Frontend" -ForegroundColor Gray
}
Write-Host ""
exit 0
