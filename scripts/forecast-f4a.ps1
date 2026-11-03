# Forecasting F4a: refresh the Chicago model before any percentage is shown in the app.
# Fresh check on never-used months, percentage check, and the new model forecast-chicago-0.2.
# Start it by double-clicking scripts\forecast-f4a.bat. About 45-60 minutes. Every part is saved: if it stops, run it again.
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $(Get-Date -Format HH:mm) $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Step "1/3 Reading database user and password from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast"
Write-Host "OK (database 'forecast', separate from the app database)"

Step "2/3 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }

$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }
Set-Location (Join-Path $root "ml")

Step "3/3 F4a refresh: extended learning table (15-30 min), fresh check, percentage check, model 0.2"
Write-Host "Progress is shown below. If it stops for any reason, double-click this file again: it continues where it stopped." -ForegroundColor Yellow
$env:PYTHONUNBUFFERED = "1"
& $venvPython -u -m forecasting.run f4a-refresh
if ($LASTEXITCODE -ne 0) { Fail "The refresh stopped (message above). Double-click again to continue; tell Claude if it repeats." }

$report = Join-Path $root "ml\forecasting\reports\chicago\f4a-refresh-report.md"
Write-Host ""
Write-Host "ALL DONE $(Get-Date -Format HH:mm). Report: $report" -ForegroundColor Green
Write-Host "Tell Claude 'F4a finished' to read it together. Nothing changes in the app until you decide."
Start-Process notepad.exe $report
