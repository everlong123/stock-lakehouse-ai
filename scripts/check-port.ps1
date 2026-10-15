$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($c) {
    $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    "port 8000 pid=" + $c.OwningProcess + " name=" + $p.ProcessName | Out-File -FilePath d:\School\kltn\stock-lakehouse-ai\scripts\check.log -Append
} else {
    "port 8000: not in Get-NetTCPConnection" | Out-File -FilePath d:\School\kltn\stock-lakehouse-ai\scripts\check.log -Append
}

"--- wmic process where name=python.exe ---" | Out-File -FilePath d:\School\kltn\stock-lakehouse-ai\scripts\check.log -Append
$w = wmic process where "name='python.exe'" get ProcessId,CommandLine /format:list 2>&1
$w | Out-File -FilePath d:\School\kltn\stock-lakehouse-ai\scripts\check.log -Append
