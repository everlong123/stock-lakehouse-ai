# stop-all.ps1
# Dừng toàn bộ dev stack (backend + frontend + tuỳ chọn Docker + tuỳ chọn WSL).
# Usage:
#   powershell -ExecutionPolicy Bypass -File stop-all.ps1             # chỉ dev
#   powershell -ExecutionPolicy Bypass -File stop-all.ps1 -All        # dev + docker
#   powershell -ExecutionPolicy Bypass -File stop-all.ps1 -DockerOnly # chỉ docker
#
# Mặc định (không flag): chỉ kill tiến trình dev, Docker containers VẪN chạy
# nên lần sau khởi động nhanh hơn. Truyền -All để tắt tất cả cho gọn RAM/CPU.

param(
    [switch]$All,        # dev + docker
    [switch]$DockerOnly, # chỉ docker, không đụng dev
    [switch]$Wsl         # chỉ tắt WSL (giải phóng vmmemWSL)
)

$ErrorActionPreference = "SilentlyContinue"
$root = $PSScriptRoot
$distro = "Ubuntu-24.04"

function Stop-Dev {
    Write-Host "[1/2] Stopping backend (uvicorn)..." -ForegroundColor Yellow
    Get-WmiObject Win32_Process -Filter "name='python.exe'" | Where-Object {
        $_.CommandLine -like '*uvicorn app.main*'
    } | ForEach-Object {
        try {
            Write-Host "  Killing PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        } catch {}
    }

    # Kill the CPU-bound job workers as well. They are spawned children of
    # uvicorn and on Windows they do NOT always die with their parent. An
    # orphan keeps a handle on the shared log file, which blocks the parent's
    # log rotation (Windows cannot rename a file that is open elsewhere) and
    # silently drops every log record after the 5 MB mark.
    Get-WmiObject Win32_Process -Filter "name='python.exe'" | Where-Object {
        $_.CommandLine -like '*multiprocessing.spawn*'
    } | ForEach-Object {
        try {
            Write-Host "  Killing worker PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        } catch {}
    }

    Write-Host "[2/2] Stopping frontend (vite)..." -ForegroundColor Yellow
    Get-WmiObject Win32_Process -Filter "name='node.exe'" | Where-Object {
        $_.CommandLine -match 'vite' -and $_.CommandLine -notmatch 'Cursor'
    } | ForEach-Object {
        try {
            Write-Host "  Killing PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

function Invoke-Wsl {
    # Runs a command inside the distro with a hard timeout.
    #
    # WHY a timeout is needed: when `vmmemWSL` is sitting at its 12GB cap the
    # guest stops accepting new wsl.exe calls at all - every command comes back
    # `WSAETIMEDOUT` after the full default timeout. Observed on 2026-10-28
    # 00:26, where `docker compose stop` failed with exit -1 for exactly this
    # reason. Without a bounded call, `stop-all.ps1` hangs for minutes.
    param(
        [string]$Command,
        [int]$TimeoutSec = 45
    )
    $job = Start-Job -ScriptBlock {
        param($d, $c)
        $out = & wsl.exe -d $d -u root -- bash -lc $c 2>&1
        [pscustomobject]@{ Output = @($out); ExitCode = $LASTEXITCODE }
    } -ArgumentList $distro, $Command

    if (Wait-Job $job -Timeout $TimeoutSec) {
        $res = Receive-Job $job
        Remove-Job $job -Force
        $code = if ($res -is [array]) { $res[-1].ExitCode } else { $res.ExitCode }
        return [pscustomobject]@{
            Output   = @($res | ForEach-Object { $_.Output })
            ExitCode = $code
            Ok       = ($code -eq 0)
            TimedOut = $false
        }
    }
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force
    return [pscustomobject]@{ Output = @(); ExitCode = -1; Ok = $false; TimedOut = $true }
}

function Stop-Docker {
    param([string]$Mode)
    if (-not (Test-Path (Join-Path $root "docker-compose.yml"))) {
        Write-Host "[docker] docker-compose.yml not found in $root" -ForegroundColor Red
        return
    }
    Write-Host "[docker] Stopping containers ($Mode profile)..." -ForegroundColor Yellow

    # The `docker` CLI on PATH is Docker Desktop's, and Docker Desktop is NOT
    # running on this box - the real engine is the native `dockerd` inside the
    # WSL2 distro (started by systemd on boot). So drive compose through wsl.exe.
    $wslRoot = "/mnt/d/School/kltn/stock-lakehouse-ai"
    $compose = "cd $wslRoot && docker compose --profile $Mode stop"

    $res = Invoke-Wsl -Command $compose -TimeoutSec 45
    if ($res.Ok) {
        $res.Output | ForEach-Object { Write-Host "  $_" }
        Write-Host "[docker] Containers stopped (named volumes PRESERVED)." -ForegroundColor Green
        return
    }

    if ($res.TimedOut) {
        Write-Host "  wsl timed out (guest unresponsive under memory pressure)." -ForegroundColor Yellow
    } else {
        Write-Host "  wsl docker compose failed." -ForegroundColor Yellow
    }

    # Best-effort fallback. In -All mode this is not fatal: `wsl --terminate`
    # right after kills the distro and every container with it anyway.
    Write-Host "  trying Windows docker CLI as fallback..." -ForegroundColor Yellow
    Push-Location $root
    try {
        & docker compose --profile $Mode stop 2>&1 | ForEach-Object { Write-Host "  $_" }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[docker] Containers stopped via Windows CLI." -ForegroundColor Green
            return
        }
    } finally {
        Pop-Location
    }
    Write-Host "[docker] Could not stop containers gracefully (they will die with the VM on -Wsl/-All)." -ForegroundColor Yellow
}

function Stop-WslVm {
    # Frees the RAM held by `vmmemWSL`. On this box the VM is capped at 12GB
    # (.wslconfig) but `autoMemoryReclaim=gradual` only hands memory back in
    # small steps, so it can sit at ~12GB while the guest is actually idle.
    # `wsl --terminate` is a hard stop: it kills the distro, the dockerd inside
    # it and every container. Named volumes (MySQL data, MinIO buckets) live on
    # the Windows disk, so they survive.
    Write-Host "[wsl] Terminating $distro (frees vmmemWSL)..." -ForegroundColor Yellow

    # Disable the keepalive task FIRST - it holds an attached wsl.exe session
    # and its trigger fires every minute. Merely stopping it is not enough:
    # the next repetition re-attaches and brings the VM straight back up.
    $taskName = "WSL-Distro-Keepalive"
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.State -ne "Disabled") {
            Write-Host "  Disabling scheduled task '$taskName'..." -ForegroundColor Yellow
            Disable-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
        }
        if ($task.State -eq "Running") {
            Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
        }
        Start-Sleep -Seconds 2
    }

    & wsl.exe --terminate $distro 2>&1 | ForEach-Object { Write-Host "  $_" }

    # `wsl --terminate <distro>` only stops THAT distro - the WSL2 VM itself
    # keeps running, and `vmmemWSL` keeps its working set. On this box the VM
    # is pinned at its 12GB cap because `.wslconfig` sets
    # `vmIdleTimeout=-1` (needed so the dockerd inside the distro survives
    # between refresh passes), so the memory is never handed back on its own.
    #
    # `wsl --shutdown` stops the VM and every distro in it, which is what
    # actually frees `vmmemWSL`. Both distros are already stopped at this
    # point, so this costs nothing extra.
    Write-Host "  shutting down the WSL2 VM (frees vmmemWSL)..." -ForegroundColor Yellow
    & wsl.exe --shutdown 2>&1 | ForEach-Object { Write-Host "  $_" }

    # The VM does not release its memory instantly - `vmmemWSL` is torn down
    # asynchronously and keeps its working set for a few seconds. Measured on
    # 2026-10-28 00:26: 11353 MB right after terminate, ~1000 MB a minute
    # later. So poll instead of reporting the first reading as "still present".
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Seconds 5
        $vmmem = Get-Process -Name "vmmemWSL" -ErrorAction SilentlyContinue
        if (-not $vmmem) { break }
        $mb = [int]($vmmem.WorkingSet64/1MB)
        Write-Host ("  vmmemWSL: {0} MB (reclaiming...)" -f $mb) -ForegroundColor DarkGray
        if ($mb -lt 2048) { break }
    }
    $vmmem = Get-Process -Name "vmmemWSL" -ErrorAction SilentlyContinue
    if ($vmmem) {
        $mb = [int]($vmmem.WorkingSet64/1MB)
        if ($mb -lt 2048) {
            Write-Host ("[wsl] vmmemWSL down to {0} MB." -f $mb) -ForegroundColor Green
        } else {
            Write-Host ("[wsl] vmmemWSL still at {0} MB." -f $mb) -ForegroundColor Yellow
        }
    } else {
        Write-Host "[wsl] vmmemWSL released." -ForegroundColor Green
    }
}

if ($Wsl) {
    Stop-WslVm
} elseif ($DockerOnly) {
    Stop-Docker -Mode "all"
} elseif ($All) {
    Stop-Dev
    # Stop the containers FIRST (graceful, so the DB flushes cleanly), then
    # terminate the VM. `wsl --terminate` kills the containers as a side
    # effect, so if compose fails because the guest is already unresponsive,
    # the containers still go down - just not gracefully.
    Stop-Docker -Mode "all"
    Stop-WslVm
} else {
    Stop-Dev
    Write-Host ""
    Write-Host "Dev processes stopped. Docker containers still running." -ForegroundColor Cyan
    Write-Host "  - To also stop Docker:  .\stop-all.ps1 -All" -ForegroundColor Cyan
    Write-Host "  - To free vmmemWSL:     .\stop-all.ps1 -Wsl" -ForegroundColor Cyan
    Write-Host "  - To start again:       .\start-all.ps1" -ForegroundColor Cyan
}
Write-Host "Done." -ForegroundColor Green

