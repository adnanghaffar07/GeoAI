# Forecasting F2: build the learning table, train B0 / B1 / M, write the VALIDATION report.
# Start it by double-clicking scripts\forecast-f2.bat. The locked test is NOT run here (forecast-f2-test.bat, once).
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

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

Step "3/5 Preparing Python (installs the training packages the first time)"
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }

Set-Location (Join-Path $root "ml")
Write-Host "Progress is shown below. If it stops for any reason, just double-click this file again: it continues where it stopped." -ForegroundColor Yellow
Step "4/5 Building the learning table (about 10-30 minutes; saved year by year)"
& $venvPython -m forecasting.run f2-build
if ($LASTEXITCODE -ne 0) { Fail "Building the learning table stopped (message above). Double-click again to continue from the last saved part." }

Step "5/5 Training B0, B1 and the main model, then scoring the validation year (about 10-30 minutes)"
& $venvPython -m forecasting.run f2-train
if ($LASTEXITCODE -ne 0) { Fail "Training stopped (message above). Double-click again to continue from the last saved part." }

$report = Join-Path $root "ml\forecasting\reports\chicago\f2-validation-report.md"
Write-Host ""
Write-Host "ALL DONE. Validation report: $report" -ForegroundColor Green
Write-Host "The locked test was NOT run. Tell Claude 'F2 validation finished' to read the report together."
Start-Process notepad.exe $report
