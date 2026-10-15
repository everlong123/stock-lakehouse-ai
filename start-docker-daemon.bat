@echo off
REM start-docker-daemon.bat
REM Start Docker daemon without Docker Desktop UI (lightweight mode).
REM Requires: Run as Administrator.

setlocal

echo.
echo === Stopping Docker Desktop UI (frees RAM) ===
taskkill /F /IM "Docker Desktop.exe" 2>nul
timeout /t 2 /nobreak >nul

echo === Killing stale dockerd.exe ===
taskkill /F /IM dockerd.exe 2>nul
timeout /t 2 /nobreak >nul

set DOCKERD="C:\Program Files\Docker\Docker\resources\bin\dockerd.exe"
if not exist %DOCKERD% (
    echo [ERROR] dockerd.exe not found at %DOCKERD%
    exit /b 1
)

echo === Starting dockerd.exe (daemon only, no UI) ===
start "dockerd" /B %DOCKERD% ^
    --exec-root="C:\ProgramData\Docker" ^
    --data-root="C:\ProgramData\Docker\data" ^
    --host=npipe:////./pipe/docker_engine ^
    --pidfile="C:\ProgramData\Docker\docker.pid"

echo === Waiting for daemon to become ready (max 60s) ===
set READY=0
for /L %%i in (1,1,30) do (
    timeout /t 2 /nobreak >nul
    docker info 2>&1 | findstr /C:"Server Version" >nul
    if not errorlevel 1 (
        echo [OK] Docker daemon is ready.
        set READY=1
        goto :ready
    )
    echo [%%i] still waiting...
)

:ready
if %READY%==0 (
    echo [ERROR] Daemon did not start in 60s. Check Event Viewer.
    exit /b 1
)

echo.
echo Docker daemon is up. You can now run docker compose commands.
echo To stop later: taskkill /F /IM dockerd.exe
endlocal