# Forecasting any-area step: Level 1 risk factors for one area (default: Naperville, owner decision D2).
# Area check (boundary, weather stations, roads) -> downloads -> load -> Level 1 report. About 10-20 minutes.
# Start it by double-clicking scripts\forecast-area.bat. Safe to run again (finished downloads are skipped).
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

$area = (Read-Host "Area name (press Enter for naperville)").Trim().ToLower()
if (-not $area) { $area = "naperville" }
if (-not (Test-Path (Join-Path $root "ml\forecasting\config\areas\$area.yaml"))) { Fail "No area file ml\forecasting\config\areas\$area.yaml. Ask Claude to add one." }

Step "1/6 Reading database user and password from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast"
Write-Host "OK (database 'forecast', separate from the app database)"

Step "2/6 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }

$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }
Set-Location (Join-Path $root "ml")

Step "3/6 Area check: boundary, weather stations (rule D3) and roads"
& $venvPython -m forecasting.run --area $area area-check
if ($LASTEXITCODE -ne 0) { Fail "The area check stopped (message above). Double-click again later; tell Claude if it repeats." }

Step "4/6 Downloading elevation, flood zones, soil and traffic for the area"
& $venvPython -m forecasting.run --area $area download
if ($LASTEXITCODE -eq 3) { Write-Host "Some downloads failed (listed above). Loading everything else; run this again later to fill the gaps." -ForegroundColor Yellow }
elseif ($LASTEXITCODE -ne 0) { Fail "Download stopped (message above). Run this again later; finished files are kept." }

Step "5/6 Loading into the area's own schema of the forecast database"
& $venvPython -m forecasting.run --area $area load
if ($LASTEXITCODE -ne 0) { Fail "Load stopped (message above)." }

Step "6/6 Level 1 risk factors"
& $venvPython -m forecasting.run --area $area level1
if ($LASTEXITCODE -ne 0) { Fail "Level 1 stopped (message above)." }

$report = Join-Path $root "ml\forecasting\reports\$area\level1-risk-factors.md"
Write-Host ""
Write-Host "ALL DONE. Reports in ml\forecasting\reports\$area\ (area-check.md and level1-risk-factors.md)." -ForegroundColor Green
Write-Host "Tell Claude '$area finished' to read them together."
Start-Process notepad.exe $report
