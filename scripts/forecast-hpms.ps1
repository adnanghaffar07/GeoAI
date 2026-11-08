# US plan step B: download HPMS road condition (FHWA, free) for one area and match it to its road sections.
# Use it for areas set up before step B (Chicago, Naperville); projects set up again (switch off and on) get HPMS by themselves.
# Start it by double-clicking scripts\forecast-hpms.bat. About 1-5 minutes. Safe to run again.
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

$area = (Read-Host "Area name (press Enter for chicago)").Trim().ToLower()
if (-not $area) { $area = "chicago" }

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

Step "3/3 Downloading HPMS for $area and matching it to the road sections"
& $venvPython -m forecasting.run --area $area hpms
if ($LASTEXITCODE -ne 0) { Fail "HPMS did not finish (FHWA's server is sometimes slow or full). Wait 10 minutes and run this again." }
Write-Host ""
Write-Host "DONE. In the app: Settings > Road risk > Update now, then the roads show 'measured by the state' factors." -ForegroundColor Green
