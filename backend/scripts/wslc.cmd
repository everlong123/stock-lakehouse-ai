@echo off
REM Run wsl.exe without flashing a console window.
REM
REM Usage:
REM   wslc -d Ubuntu-24.04 -u root -- bash -lc "docker ps"
REM   wslc --no-wait -d Ubuntu-24.04 -- long-running-job
REM
REM Put this directory on PATH, or call it by full path.
REM See wslc.vbs for the details and the rationale.

setlocal EnableDelayedExpansion

if "%~1"=="" (
    echo usage: wslc [--no-wait] ^<wsl arguments...^>
    exit /b 2
)

set "WSLC_VBS=%~dp0wslc.vbs"
if not exist "%WSLC_VBS%" set "WSLC_VBS=D:\School\kltn\stock-lakehouse-ai\backend\scripts\wslc.vbs"

REM A hidden window has no console to print to, so stdout has to be captured
REM explicitly and echoed back into the caller's console. The temp file is
REM removed afterwards.
set "WSLC_OUT=%TEMP%\wslc-%RANDOM%.tmp"
set "WSLC_ERR=%TEMP%\wslc-%RANDOM%.tmp"

wscript.exe "%WSLC_VBS%" --redirect "%WSLC_OUT%" --redirect-err "%WSLC_ERR%" %*
set "WSLC_RC=%ERRORLEVEL%"

if exist "%WSLC_OUT%" (
    type "%WSLC_OUT%"
    del /q "%WSLC_OUT%" >nul 2>&1
)
if exist "%WSLC_ERR%" (
    type "%WSLC_ERR%" 1>&2
    del /q "%WSLC_ERR%" >nul 2>&1
)

endlocal & exit /b %WSLC_RC%
