# stop-all.ps1
# Dừng toàn bộ dev stack (backend + frontend).
# Usage: powershell -ExecutionPolicy Bypass -File stop-all.ps1

Write-Host "Stopping backend (uvicorn)..." -ForegroundColor Yellow
Get-WmiObject Win32_Process -Filter "name='python.exe'" | Where-Object {
    $_.CommandLine -like '*uvicorn app.main*'
} | ForEach-Object {
    try {
        Write-Host "  Killing PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
}

Write-Host "Stopping frontend (vite)..." -ForegroundColor Yellow
Get-WmiObject Win32_Process -Filter "name='node.exe'" | Where-Object {
    $_.CommandLine -match 'vite' -and $_.CommandLine -notmatch 'Cursor'
} | ForEach-Object {
    try {
        Write-Host "  Killing PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
}

Write-Host "Done." -ForegroundColor Green
