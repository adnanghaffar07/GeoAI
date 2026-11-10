# US plan step C: download a city's pothole history again (after its area file changed), load the area, redo Level 1.
# Start it by double-clicking scripts\forecast-city-refresh.bat. About 5-15 minutes. Safe to run again.
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

$area = (Read-Host "Area name (press Enter for boston)").Trim().ToLower()
if (-not $area) { $area = "boston" }

Step "1/5 Reading database user and password from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast"
Write-Host "OK (database 'forecast', separate from the app database)"

Step "2/5 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }

$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }
Set-Location (Join-Path $root "ml")

Step "3/5 Downloading the pothole history of $area again"
& $venvPython -m forecasting.run --area $area download --only potholes_city --force
if ($LASTEXITCODE -ne 0) { Fail "The download did not finish. Run this again later." }
Step "4/5 Loading $area"
& $venvPython -m forecasting.run --area $area load
if ($LASTEXITCODE -ne 0) { Fail "Loading did not finish. Send Claude the messages above." }
Step "5/5 Level 1 risk factors"
& $venvPython -m forecasting.run --area $area level1
if ($LASTEXITCODE -ne 0) { Fail "Level 1 did not finish. Send Claude the messages above." }
Write-Host ""
Write-Host "DONE. Tell Claude 'city refresh finished'." -ForegroundColor Green
