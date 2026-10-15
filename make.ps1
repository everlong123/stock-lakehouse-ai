# make.ps1 - Windows wrapper. Usage: .\make.ps1 <target>
$DC = "docker compose"
$Target = $args[0]; if (-not $Target) { $Target = "help" }
function Show-Help {
    Write-Host "Stock Lakehouse - make.ps1" -ForegroundColor Cyan
    Write-Host "Targets: up-infra up-app up-all down down-infra down-app ps logs health rebuild nuke help" -ForegroundColor Yellow
}
switch ($Target) {
    "help"     { Show-Help }
    "up-infra" { & docker compose --profile infra up -d; Write-Host "[OK] Wait 30s then run: .\make.ps1 health" -ForegroundColor Cyan }
    "up-app"   { & docker compose --profile app up -d; Write-Host "[OK] Wait 60s then run: .\make.ps1 health" -ForegroundColor Cyan }
    "up-all"   { & docker compose --profile all up -d; Write-Host "[OK] Wait 90s then run: .\make.ps1 health" -ForegroundColor Cyan }
    "down"     { & docker compose --profile all down }
    "down-infra" { & docker compose --profile infra stop }
    "down-app"   { & docker compose --profile app stop }
    "ps"       { & docker compose --profile all ps }
    "logs"     { & docker compose --profile all logs -f --tail=100 }
    "logs-infra" { & docker compose --profile infra logs -f --tail=100 }
    "logs-app"   { & docker compose --profile app logs -f --tail=100 }
    "health"   { & docker compose --profile all ps --format "table {{.Service}}	{{.State}}	{{.Status}}"; Write-Host ""; try { (Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 5) | ConvertTo-Json } catch { Write-Host "Backend: DOWN" -ForegroundColor Red } }
    "rebuild"  { & docker compose --profile app up -d --build }
    default    { Write-Host "Unknown: $Target" -ForegroundColor Red; Show-Help }
}
