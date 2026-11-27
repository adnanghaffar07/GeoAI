# Read-only, step-by-step check of the free road-condition services (FHWA HPMS, Cook County pavement).
# Each step prints on screen as it runs, with OK or FAIL, so you can see where it breaks. About 2-5 minutes.
# Saves only backend\road-condition-check.log.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "STOPPED: ml\.venv is missing. Run scripts\forecast-f1.bat first." -ForegroundColor Red; exit 1 }
$log = Join-Path $root "backend\road-condition-check.log"
$env:PYTHONUNBUFFERED = "1"
Write-Host "Starting the check... the first line appears in a few seconds." -ForegroundColor Cyan
& $py -u (Join-Path $root "ml\forecasting\road_condition_check.py") 2>&1 | Tee-Object -FilePath $log
Write-Host ""
Write-Host "Done. Send Claude the text above (or backend\road-condition-check.log)." -ForegroundColor Green
