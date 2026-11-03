@echo off
REM stop-all.bat
REM Stops the dev stack (backend + frontend) started by start-all.bat.
REM
REM Extra flags are passed through to stop-all.ps1:
REM   stop-all.bat -All    dev + docker containers + WSL (frees vmmemWSL RAM)
REM   stop-all.bat -Wsl    just terminate the WSL VM (frees vmmemWSL RAM)
REM   stop-all.bat -DockerOnly   just stop the docker containers
REM
REM NOTE: "stop-all.bat" on its own only stops the dev processes; Docker
REM containers keep running. Use -All (or -Wsl) to also release vmmemWSL.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File ".\stop-all.ps1" %*
pause
