$ports = 8123,5173,3000,8000,8080
foreach ($p in $ports) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        Write-Host ("Port " + $p + " LISTENING (pid=" + $c.OwningProcess + ")")
    } else {
        Write-Host ("Port " + $p + " free")
    }
}

Write-Host ""
Write-Host "--- uvicorn processes ---"
Get-WmiObject Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn app.main*' } |
    ForEach-Object { Write-Host ("uvicorn pid=" + $_.ProcessId + " cmd=" + $_.CommandLine.Substring(0, [Math]::Min(120, $_.CommandLine.Length))) }

Write-Host ""
Write-Host "--- vite processes ---"
Get-WmiObject Win32_Process -Filter "name='node.exe'" |
    Where-Object { $_.CommandLine -match 'vite' -and $_.CommandLine -notmatch 'Cursor' } |
    ForEach-Object { Write-Host ("vite pid=" + $_.ProcessId + " cmd=" + $_.CommandLine.Substring(0, [Math]::Min(120, $_.CommandLine.Length))) }

if (-not (Get-WmiObject Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' })) {
    Write-Host ""
    Write-Host "No uvicorn running." -ForegroundColor Yellow
}
if (-not (Get-WmiObject Win32_Process -Filter "name='node.exe'" | Where-Object { $_.CommandLine -match 'vite' -and $_.CommandLine -notmatch 'Cursor' })) {
    Write-Host ""
    Write-Host "No vite running." -ForegroundColor Yellow
}
