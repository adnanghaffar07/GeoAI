# Naperville plan N3: the LOCKED transfer test. Runs the Chicago model (unchanged, read only) on Naperville's roads for
# every Monday since 2025-01-06 and checks it against Naperville's own pothole reports, with Chicago's pass marks.
# Runs ONCE (a second run is refused). Writes ml\forecasting\reports\naperville\transfer-test.md. About 5-20 minutes.
# Changes nothing in Chicago, Boston, Philadelphia or the app; in Naperville it only rebuilds report_matches.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

$area = (Read-Host "Area name (press Enter for naperville)").Trim().ToLower()
if (-not $area) { $area = "naperville" }

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

$answer = (Read-Host "This locked test runs only once. Type YES to run it now").Trim()
if ($answer -ne "YES") { Fail "Not started (you did not type YES)." }
Step "3/3 Running the transfer test for $area"
& $venvPython -u -m forecasting.run --area $area transfer-test --owner-go-ahead
if ($LASTEXITCODE -ne 0) { Fail "The transfer test did not finish. Send the lines above to Claude." }
Write-Host ""
Write-Host "DONE. Send ml\forecasting\reports\naperville\transfer-test.md to Claude." -ForegroundColor Green
