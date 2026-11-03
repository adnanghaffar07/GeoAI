# Forecasting F4b: check that the app's one-Monday inputs equal the learning table's inputs exactly (5 Mondays).
# Also fills the table of which reports belong to which road (once). About 5-10 minutes.
# Start it by double-clicking scripts\forecast-weekly-check.bat. Safe to run again.
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

Step "2/3 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }

$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
Set-Location (Join-Path $root "ml")
Step "3/3 Weekly inputs check"
$env:PYTHONUNBUFFERED = "1"
& $venvPython -u -m forecasting.run weekly-check
$check = $LASTEXITCODE
if ($check -ne 0 -and $check -ne 4) { Fail "The check stopped (message above). Double-click again; tell Claude if it repeats." }
$report = Join-Path $root "ml\forecasting\reports\chicago\weekly-check.md"
Write-Host ""
if ($check -eq 0) { Write-Host "PASSED $(Get-Date -Format HH:mm). Tell Claude 'weekly check finished'." -ForegroundColor Green }
else { Write-Host "SOMETHING DIFFERS (see the report). Tell Claude 'weekly check finished'." -ForegroundColor Yellow }
Start-Process notepad.exe $report
