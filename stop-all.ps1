# stop-all.ps1
# Dừng toàn bộ dev stack (backend + frontend + tuỳ chọn Docker).
# Usage:
#   powershell -ExecutionPolicy Bypass -File stop-all.ps1             # chỉ dev
#   powershell -ExecutionPolicy Bypass -File stop-all.ps1 -All        # dev + docker
#   powershell -ExecutionPolicy Bypass -File stop-all.ps1 -DockerOnly # chỉ docker
#
# Mặc định (không flag): chỉ kill tiến trình dev, Docker containers VẪN chạy
# nên lần sau khởi động nhanh hơn. Truyền -All để tắt tất cả cho gọn RAM/CPU.

param(
    [switch]$All,        # dev + docker
    [switch]$DockerOnly  # chỉ docker, không đụng dev
)

$ErrorActionPreference = "SilentlyContinue"
$root = $PSScriptRoot

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

function Stop-Docker {
    param([string]$Mode)
    if (-not (Test-Path (Join-Path $root "docker-compose.yml"))) {
        Write-Host "[docker] docker-compose.yml not found in $root" -ForegroundColor Red
        return
    }
    Write-Host "[docker] Stopping containers ($Mode profile)..." -ForegroundColor Yellow
    Push-Location $root
    try {
        # Mặc định dùng profile all (đang có 6 containers đang chạy); nếu muốn
        # chỉ infra thì đổi profile tại đây.
        $profile = "all"
        & docker compose --profile $profile stop 2>&1 | ForEach-Object { Write-Host "  $_" }
    } finally {
        Pop-Location
    }
    Write-Host "[docker] Containers stopped (named volumes PRESERVED)." -ForegroundColor Green
}

if ($DockerOnly) {
    Stop-Docker -Mode "all"
} elseif ($All) {
    Stop-Dev
    Stop-Docker -Mode "all"
} else {
    Stop-Dev
    Write-Host ""
    Write-Host "Dev processes stopped. Docker containers still running." -ForegroundColor Cyan
    Write-Host "  - To also stop Docker:  .\stop-all.ps1 -All" -ForegroundColor Cyan
    Write-Host "  - To start again:       .\start-all.ps1" -ForegroundColor Cyan
}
Write-Host "Done." -ForegroundColor Green

