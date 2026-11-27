# Counties expansion, internal research test: the City of Aurora.
# 1) runs the two forecasting test files, 2) area check (boundary, weather stations, roads), 3) downloads, 4) load,
# 5) Level 1 risk factors, 6) downloads Aurora's pothole requests from its open data. No transfer test yet (too little data).
# Changes nothing in Chicago, Naperville, Boston, Philadelphia or the app (own schema: aurora).
# About 10-25 minutes. Safe to run again. The locked transfer test is a separate, later step.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$area = "aurora"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }


Step "1/7 Reading database user and password from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast"
Write-Host "OK (database 'forecast', separate from the app database)"

Step "2/7 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }

$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt pytest pytest-timeout
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }
Set-Location (Join-Path $root "ml")

Step "3/7 Checking the code change (forecasting tests for areas and cities)"
& $venvPython -m pytest -q -p no:cacheprovider --timeout=240 tests/test_forecast_cities.py tests/test_forecast_areas.py tests/test_forecast_download.py
if ($LASTEXITCODE -ne 0) { Fail "A test failed (lines above). Send them to Claude. Nothing was changed in the database." }

Step "4/7 Area check: boundary of the three towns, weather stations and roads"
& $venvPython -m forecasting.run --area $area area-check
if ($LASTEXITCODE -ne 0) { Fail "The area check stopped (message above). Send the lines to Claude." }

Step "5/7 Downloading elevation, flood zones, soil and traffic"
& $venvPython -m forecasting.run --area $area download
if ($LASTEXITCODE -eq 3) { Write-Host "Some downloads failed (listed above). Loading everything else." -ForegroundColor Yellow }
elseif ($LASTEXITCODE -ne 0) { Fail "Download stopped (message above). Run this again later; finished files are kept." }

Step "6/7 Loading roads and factors into the area's own schema"
& $venvPython -m forecasting.run --area $area load
if ($LASTEXITCODE -ne 0) { Fail "Load stopped (message above)." }
& $venvPython -m forecasting.run --area $area level1
if ($LASTEXITCODE -ne 0) { Fail "Level 1 stopped (message above)." }

Step "7/7 Downloading and loading Aurora's 311 pothole requests (public domain)"
& $venvPython -m forecasting.run --area $area potholes
if ($LASTEXITCODE -ne 0) { Fail "The pothole reports did not load (message above)." }

Write-Host ""
Write-Host "ALL DONE. Tell Claude 'aurora prepared'. and paste the lines above (counts)." -ForegroundColor Green
