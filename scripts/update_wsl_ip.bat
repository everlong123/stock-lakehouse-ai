@echo off
REM Auto-update WSL IP in .env.local
REM Run this after WSL restart

REM Get WSL IP
for /f "delims=" %%i in ('wsl hostname -I') do set WSL_IP=%%i
for /f "delims=" %%i in ('echo %WSL_IP%') do set WSL_IP=%%i

echo Detected WSL IP: %WSL_IP%

REM Update .env.local
setlocal enabledelayedexpansion
set "FILE=D:\School\kltn\stock-lakehouse-ai\backend\.env.local"
set "TEMP=%FILE%.tmp"

if exist "%FILE%" (
    findstr /v /c:"MINIO_ENDPOINT" "%FILE%" > "%TEMP%"
    echo MINIO_ENDPOINT=%WSL_IP%:9000 >> "%TEMP%"
    move /y "%TEMP%" "%FILE%"
    echo Updated MINIO_ENDPOINT=%WSL_IP%:9000 in .env.local
) else (
    echo .env.local not found!
)

pause
