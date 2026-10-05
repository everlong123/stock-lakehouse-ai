@echo off
REM start-all.bat
REM Double-click this file to launch the full dev stack (backend + frontend).
REM Two new cmd windows will pop up. Close this launcher when done; the
REM service windows keep running.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File ".\start-all.ps1"
