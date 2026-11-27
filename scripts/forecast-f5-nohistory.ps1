# F5 experiment: does the Chicago scorecard still work WITHOUT a road's own report history?
# Uses only the saved learning table and Chicago training/validation years. The locked test is never read.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Write-Host "STOPPED: ml\.venv is missing. Run scripts\forecast-f1.bat first." -ForegroundColor Red; exit 1 }
Set-Location (Join-Path $root "ml")
& $venvPython -m forecasting.f5_no_history
if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED: see the message above." -ForegroundColor Red; exit 1 }
$report = Join-Path $root "ml\forecasting\reports\chicago\f5-no-history-report.md"
Write-Host "ALL DONE. Report: $report" -ForegroundColor Green
Start-Process notepad.exe $report
