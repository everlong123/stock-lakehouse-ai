@echo off
REM Enable the Windows pagefile (system-managed) to stop hard crashes.
REM Right-click this file and choose "Run as administrator".

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo [1/2] Disabling automatic pagefile management so we can set it explicitly...
wmic computersystem set AutomaticManagedPagefile=False >nul 2>&1

echo [2/2] Creating a system-managed pagefile on C: ...
wmic pagefileset where name="C:\\pagefile.sys" set InitialSize=0,MaximumSize=0 >nul 2>&1
if %errorlevel% neq 0 (
  wmic pagefileset create name="C:\\pagefile.sys" >nul 2>&1
)

wmic computersystem set AutomaticManagedPagefile=True >nul 2>&1

echo.
echo Result:
wmic computersystem get AutomaticManagedPagefile
wmic pagefile get name,AllocatedBaseSize,CurrentUsage,PeakUsage
echo.
echo Pagefile enabled. A reboot is recommended for it to take full effect.
pause
