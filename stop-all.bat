@echo off
REM stop-all.bat
REM Stops the dev stack (backend + frontend) started by start-all.bat.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File ".\stop-all.ps1"
pause
