# Poll for console windows appearing, to catch the flashing popup.
# Runs for 100s, which spans at least one WSL-Distro-Keepalive task fire.
$seen = @{}
for ($i = 0; $i -lt 50; $i++) {
    $now = Get-Date
    $wins = Get-Process | Where-Object { $_.MainWindowTitle -ne "" }
    foreach ($w in $wins) {
        $key = "$($w.Id)|$($w.ProcessName)"
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $now
            Write-Output ("{0}  NEW WINDOW  pid={1}  proc={2}  title='{3}'" -f $now.ToString('HH:mm:ss'), $w.Id, $w.ProcessName, $w.MainWindowTitle)
        }
    }
    Start-Sleep -Seconds 2
}
Write-Output "--- conhost census ---"
Get-Process conhost -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("conhost pid={0} title='{1}'" -f $_.Id, $_.MainWindowTitle)
}
