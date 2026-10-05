# start-all.ps1
# Khởi động toàn bộ stack: Backend (FastAPI :8000) + Frontend (Vite :5173).
# Mỗi service chạy trong cửa sổ cmd RIÊNG (đóng cửa sổ = tắt service đó).
#
# CÁCH DÙNG (khuyến nghị - chạy trong PowerShell BÌNH THƯỜNG):
#   cd D:\School\kltn\stock-lakehouse-ai
#   powershell -ExecutionPolicy Bypass -File .\start-all.ps1
# Hoặc click đúp file start-all.bat
#
# Sau khi chạy, 2 cửa sổ cmd mới sẽ bật lên: 1 cho backend, 1 cho frontend.
# Mở trình duyệt: http://127.0.0.1:5173
# Tắt hết: chạy .\stop-all.ps1 (hoặc đóng 2 cửa sổ cmd).

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
$backend  = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Stop-Existing {
    Write-Host "[stop] Killing leftover uvicorn / vite processes..." -ForegroundColor Yellow
    Get-WmiObject Win32_Process -Filter "name='python.exe'" | Where-Object {
        $_.CommandLine -like '*uvicorn app.main*'
    } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue } catch {} }
    Get-WmiObject Win32_Process -Filter "name='node.exe'" | Where-Object {
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

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Stock Lakehouse AI - Dev Stack Launcher  " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Backend:  http://127.0.0.1:8000"           -ForegroundColor Gray
Write-Host "  Frontend: http://127.0.0.1:5173"           -ForegroundColor Gray
Write-Host "  Agent UI: http://127.0.0.1:5173/agent"     -ForegroundColor Gray
Write-Host ""

Stop-Existing

# ---- Start backend in its own persistent cmd window ----
# Use cmd's built-in `start` so the window is fully detached and survives this
# launcher exiting. The `/k` keeps the window open after the command finishes.
Write-Host "[1/2] Starting backend (uvicorn on :8000)..." -ForegroundColor Cyan
$backendCmd = "cd /d `"$backend`" && title Stock-LH Backend :8000 && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "Stock-LH-Backend", "/k", $backendCmd -WindowStyle Normal

# ---- Start frontend in its own persistent cmd window ----
Write-Host "[2/2] Starting frontend (vite on :5173)..." -ForegroundColor Cyan
$frontendCmd = "cd /d `"$frontend`" && title Stock-LH Frontend :5173 && npm run dev"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "Stock-LH-Frontend", "/k", $frontendCmd -WindowStyle Normal

Write-Host ""
Write-Host "[wait] Waiting for services to come up..." -ForegroundColor Yellow
$backendUp  = Wait-Port -Port 8000 -Name "Backend"  -TimeoutSec 30
$frontendUp = Wait-Port -Port 5173 -Name "Frontend" -TimeoutSec 30

Write-Host ""
if ($backendUp -and $frontendUp) {
    Write-Host "All services are up." -ForegroundColor Green
    Write-Host "  - Open http://127.0.0.1:5173 in your browser" -ForegroundColor Green
    Write-Host "  - Stop: run .\stop-all.ps1  (or close the 2 cmd windows)" -ForegroundColor Green
} else {
    Write-Host "Some services failed to start. Check the cmd windows for errors." -ForegroundColor Red
}
Write-Host ""
exit 0
