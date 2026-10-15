$logPath = "d:\School\kltn\stock-lakehouse-ai\scripts\port.log"
"" | Out-File -FilePath $logPath

# Try netstat with -o to get PID
$lines = netstat -ano | Select-String ":8000" | Select-String "LISTENING"
foreach ($l in $lines) {
    $l.Line | Out-File -Append -FilePath $logPath
}

# Then for each PID, dump info
$log = Get-Content $logPath
foreach ($line in $log) {
    if ($line -match "\s(\d+)$") {
        $pid = $Matches[1]
        "--- PID $pid ---" | Out-File -Append -FilePath $logPath
        tasklist /FI "PID eq $pid" /FO LIST /V 2>&1 | Out-File -Append -FilePath $logPath
    }
}
