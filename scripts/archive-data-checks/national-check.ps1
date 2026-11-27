# Read-only check before the US-wide road-risk step: can the laptop reach the free national and city
# data, how big is one project's download, and is there room? Nothing is saved or changed.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "==> Starting Docker (database, API)" -ForegroundColor Cyan
docker compose up -d --wait db queue | Out-Null
docker compose up -d api | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED: Docker did not start. Open Docker Desktop and try again." -ForegroundColor Red; exit 1 }
Write-Host "==> Checking the free data services (about 1-3 minutes)" -ForegroundColor Cyan
$log = Join-Path $root "backend\national-check.log"
docker compose exec -T api python /ml/forecasting/national_check.py 2>&1 | Tee-Object -FilePath $log
Write-Host ""
Write-Host "Done. Send Claude the file backend\national-check.log (or paste the text above)." -ForegroundColor Green
