# start-docker-daemon.ps1
# Start Docker daemon without Docker Desktop UI (lightweight mode for low-RAM machines).
# Requires: PowerShell as Administrator.
#
# Usage: powershell -ExecutionPolicy Bypass -File start-docker-daemon.ps1
#
# What it does:
#   1. Stops any running "Docker Desktop" UI process (free RAM).
#   2. Starts dockerd.exe as a background Windows service-like process.
#   3. Waits until docker info returns "Server Version".
#
# To stop later: Get-Process dockerd | Stop-Process

$ErrorActionPreference = "Continue"

# 1. Kill Docker Desktop UI if running (saves ~1GB RAM)
$dd = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if ($dd) {
    Write-Host "[+] Stopping Docker Desktop UI process (PID $($dd.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $dd.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# 2. Kill any old dockerd.exe to avoid "address in use" error
Get-Process "dockerd" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "[+] Killing stale dockerd.exe (PID $($_.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# 3. Start dockerd.exe in background
$dockerd = "C:\Program Files\Docker\Docker\resources\bin\dockerd.exe"
if (-not (Test-Path $dockerd)) {
    Write-Host "[-] dockerd.exe not found at $dockerd" -ForegroundColor Red
    exit 1
}

$args = @(
    "--exec-root=`"C:\ProgramData\Docker`""
    "--data-root=`"C:\ProgramData\Docker\data`""
    "--host=npipe:////./pipe/docker_engine"
    "--pidfile=`"C:\ProgramData\Docker\docker.pid`""
)

Write-Host "[+] Starting dockerd.exe (daemon only, no UI)..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $dockerd -ArgumentList $args -PassThru -WindowStyle Hidden
Write-Host "[+] dockerd.exe PID = $($proc.Id)" -ForegroundColor Green

# 4. Wait for daemon to be ready (poll docker info)
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $output = & docker info 2>&1 | Select-String "Server Version"
        if ($output) {
            Write-Host "[+] Docker daemon ready after ${i}*2s. $($output.Line)" -ForegroundColor Green
            $ready = $true
            break
        }
    } catch {
        # ignore
    }
    Write-Host "[ ] waiting... (${i})"
}

if (-not $ready) {
    Write-Host "[-] Docker daemon did not become ready in 60s. Check Event Viewer." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Docker daemon is up. You can now run docker compose commands." -ForegroundColor Green
Write-Host "To stop later:  Get-Process dockerd | Stop-Process" -ForegroundColor Yellow