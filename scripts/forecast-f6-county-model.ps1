# F6 experiment: do models that also learn from the counties' own pothole reports beat the Chicago model?
# Leave-one-area-out check on the five tested county areas. Development evidence only: no locked test is re-run,
# nothing in the app changes. First run builds a weekly cache per area (about 20-60 minutes); it continues after a stop.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Step "1/3 Reading database user and password from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast"

Step "2/3 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
Set-Location (Join-Path $root "ml")

Step "3/3 Running the experiment (leave this window open)"
& $venvPython -u -m forecasting.f6_county_model
if ($LASTEXITCODE -ne 0) { Fail "See the message above. Run it again: finished parts are kept." }
$report = Join-Path $root "ml\forecasting\reports\counties\f6-county-model-report.md"
Write-Host "ALL DONE. Report: $report" -ForegroundColor Green
Start-Process notepad.exe $report
