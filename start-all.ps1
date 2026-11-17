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
    # Kill the CPU-bound job worker processes too. They are spawned children
    # of uvicorn; on Windows they do NOT always die with their parent, and an
    # orphan keeps a handle on the shared log file, which blocks the parent's
    # log rotation (Windows cannot rename a file that is open elsewhere) and
    # silently drops every log record after the 5 MB mark.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.CommandLine -like '*multiprocessing.spawn*'
    } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue } catch {} }
    Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object {
        $_.CommandLine -match 'vite' -and $_.CommandLine -notmatch 'Cursor'
    } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue } catch {} }
    Start-Sleep -Seconds 1
}

function Get-PortOwner {
    # Returns the name of the process listening on $Port, or $null.
    # Used to tell "our uvicorn is up" apart from "something else already
    # holds this port" (e.g. the backend container publishing 8000:8000).
    param([int]$Port)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if (-not $conns) { return $null }
        $names = @()
        foreach ($c in $conns) {
            $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($p) { $names += $p.ProcessName }
        }
        if (-not $names) { return $null }
        return ($names | Select-Object -Unique) -join ","
    } catch {
        return $null
    }
}

function Wait-Port {
    param([int]$Port, [string]$Name, [int]$TimeoutSec = 30, [string]$ExpectProcess = "")
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(500, $false)
            $client.Close()
            if ($ok) {
                if ($ExpectProcess) {
                    $owner = Get-PortOwner -Port $Port
                    if ($owner -and $owner -notmatch $ExpectProcess) {
                        # Something else already owns this port - almost always
                        # a container. The local service cannot have bound it.
                        Write-Host "  [FAIL] :$Port is held by '$owner', not $ExpectProcess" -ForegroundColor Red
                        return $false
                    }
                }
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

# ---- Re-enable the WSL keepalive task ----
# `stop-all.ps1 -Wsl` disables it (the trigger fires every minute, so merely
# stopping the task lets the next repetition re-attach and bring the VM back).
# Docker lives inside the WSL2 distro, so without this task the distro is torn
# down when the last wsl.exe client exits, and every container dies with it -
# which shows up as "connect failed" on the backend and the frontend.
$keepalive = Get-ScheduledTask -TaskName "WSL-Distro-Keepalive" -ErrorAction SilentlyContinue
if ($keepalive -and $keepalive.State -eq "Disabled") {
    Write-Host "[wsl] Re-enabling 'WSL-Distro-Keepalive'..." -ForegroundColor Cyan
    Enable-ScheduledTask -TaskName "WSL-Distro-Keepalive" -ErrorAction SilentlyContinue | Out-Null
    # Re-query: the object above still carries the old State.
    $keepalive = Get-ScheduledTask -TaskName "WSL-Distro-Keepalive" -ErrorAction SilentlyContinue
}
if ($keepalive -and $keepalive.State -eq "Ready") {
    Write-Host "[wsl] Starting 'WSL-Distro-Keepalive'..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName "WSL-Distro-Keepalive" -ErrorAction SilentlyContinue | Out-Null
    Start-Sleep -Seconds 2
}

# ---- Kick the daily refresh off now ----
# The scheduled task fires at 06:00, when nothing is running yet, so it
# always found the API down and the day was silently missed. Now that
# backend/daily_refresh.py waits for the API to come up, the task is safe on
# its own - but the run is much more useful right after the stack starts, so
# the launcher triggers it here too. The task itself is Hidden and runs under
# pythonw.exe, so nothing pops up on screen.
$dailyRefresh = Get-ScheduledTask -TaskName "Stock-LH-DailyRefresh" -ErrorAction SilentlyContinue
if ($dailyRefresh -and $dailyRefresh.State -ne "Running") {
    Write-Host "[refresh] Triggering 'Stock-LH-DailyRefresh'..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName "Stock-LH-DailyRefresh" -ErrorAction SilentlyContinue | Out-Null
}

# ---- Bring the infra containers back up ----
# `docker compose stop` marks a container as manually stopped, so
# `restart: unless-stopped` will NOT bring it back - only `compose up -d` does.
# Without this step the infra (mysql/minio) stays down and
# the backend fails to connect to MySQL.
#
# Named services, NOT `--profile all`: the `backend` container publishes
# 8000:8000 and the `frontend` container 8081:80, so bringing them up steals
# the port from the local dev uvicorn/vite that this script starts right
# after. The symptom is subtle: `Wait-Port` sees the port already open (the
# container owns it) and reports "[OK] Backend listening" even though the
# local uvicorn died with "address already in use".
#
# `--no-deps` is REQUIRED, not just an optimisation: without it, compose
# pulls the backend container up as a side effect and it takes :8000 away
# from the local dev backend.
#
# WHY ONLY mysql AND minio: Apache Kafka and Apache Iceberg were removed
# from the project on 10/11/2026, so there is no broker and no catalog to
# start. The `scheduler` container (cron) is also left alone here: on this
# workstation the batch is driven by the in-process refresh thread, and the
# cron container would fetch the same symbols at the same time.
Write-Host "[docker] Starting infra containers..." -ForegroundColor Cyan
$wslRoot = "/mnt/d/School/kltn/stock-lakehouse-ai"
$composeUp = "cd $wslRoot && docker compose up -d --no-deps --wait --wait-timeout 120 mysql minio"

# Release :8000 / :8081 first in case the app containers are still up from a
# previous session - they must not hold those ports.
$composeDownApp = "cd $wslRoot && docker compose stop backend frontend"

function Invoke-Compose {
    param([string]$Command, [int]$TimeoutSec = 180)
    $job = Start-Job -ScriptBlock {
        param($d, $c)
        $out = & wsl.exe -d $d -u root -- bash -lc $c 2>&1
        [pscustomobject]@{ Output = @($out); ExitCode = $LASTEXITCODE }
    } -ArgumentList "Ubuntu-24.04", $Command
    if (Wait-Job $job -Timeout $TimeoutSec) {
        $res = Receive-Job $job
        Remove-Job $job -Force
        $code = if ($res -is [array]) { $res[-1].ExitCode } else { $res.ExitCode }
        return [pscustomobject]@{ Output = @($res | ForEach-Object { $_.Output }); ExitCode = $code }
    }
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force
    return [pscustomobject]@{ Output = @(); ExitCode = -1 }
}

# Release :8000 / :8081 first in case the app containers are still up from a
# previous session - they must not hold those ports.
Invoke-Compose -Command $composeDownApp -TimeoutSec 60 | Out-Null

$job = Start-Job -ScriptBlock {
    param($d, $c)
    $out = & wsl.exe -d $d -u root -- bash -lc $c 2>&1
    [pscustomobject]@{ Output = @($out); ExitCode = $LASTEXITCODE }
} -ArgumentList "Ubuntu-24.04", $composeUp
if (Wait-Job $job -Timeout 180) {
    $res = Receive-Job $job
    Remove-Job $job -Force
    $code = if ($res -is [array]) { $res[-1].ExitCode } else { $res.ExitCode }
    if ($code -eq 0) {
        Write-Host "  [OK] Infra containers up." -ForegroundColor Green
    } else {
        $res | ForEach-Object { $_.Output } | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        Write-Host "  [WARN] compose up returned exit $code - continuing; the backend will report what it cannot reach." -ForegroundColor Yellow
    }
} else {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force
    Write-Host "  [WARN] compose up timed out after 180s." -ForegroundColor Yellow
}

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
$backendUp  = Wait-Port -Port $backendPort  -Name "Backend"  -TimeoutSec 30 -ExpectProcess "python"
$frontendUp = Wait-Port -Port $frontendPort -Name "Frontend" -TimeoutSec 45 -ExpectProcess "node"

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
