# Auto-update WSL IP for MinIO connectivity
# Add this to your Windows startup or run manually

$wsl_ip = (wsl hostname -I).Split()[0]
$env_file = "D:\School\kltn\stock-lakehouse-ai\backend\.env.local"

Write-Host "Detected WSL IP: $wsl_ip"

if (Test-Path $env_file) {
    $content = Get-Content $env_file -Raw
    if ($content -match 'MINIO_ENDPOINT=\S+') {
        $content = $content -replace 'MINIO_ENDPOINT=\S+', "MINIO_ENDPOINT=$wsl_ip`:9000"
    } else {
        $content += "`nMINIO_ENDPOINT=$wsl_ip`:9000"
    }
    Set-Content -Path $env_file -Value $content -NoNewline
    Write-Host "Updated MINIO_ENDPOINT to $wsl_ip`:9000"
} else {
    Write-Host ".env.local not found!"
}
