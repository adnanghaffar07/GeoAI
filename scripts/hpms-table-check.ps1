# Read-only, step-by-step check: is HPMS 2024 (FHWA table on data.transportation.gov) usable for Illinois?
# Each step prints on screen as it runs. About 1-3 minutes. Saves only backend\hpms-table-check.log.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "STOPPED: ml\.venv is missing. Run scripts\forecast-f1.bat first." -ForegroundColor Red; exit 1 }
$log = Join-Path $root "backend\hpms-table-check.log"
$env:PYTHONUNBUFFERED = "1"
Write-Host "Starting the check... the first line appears in a few seconds." -ForegroundColor Cyan
& $py -u (Join-Path $root "ml\forecasting\hpms_table_check.py") 2>&1 | Tee-Object -FilePath $log
Write-Host ""
Write-Host "Done. Send Claude the text above (or backend\hpms-table-check.log)." -ForegroundColor Green
