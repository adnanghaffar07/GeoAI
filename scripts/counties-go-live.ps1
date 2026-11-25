# One run for DuPage + Cook suburbs: reload their SeeClickFix pothole reports, run the forecasting tests,
# then the backend tests LAST (they restart the backend, so the Cloudflare tunnel must be updated after).
# Double-click scripts\counties-go-live.bat. About 15-25 minutes. Results: ml\forecast-tests.log, backend\backend-tests.log
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Step($text) { Write-Host ""; Write-Host "==> $(Get-Date -Format HH:mm) $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Step "1/4 Reading database settings and starting the database"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt pytest pytest-timeout
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }

Step "2/4 Reloading the pothole reports (DuPage, then Cook suburbs; about 3-5 minutes each, slow on purpose)"
Set-Location (Join-Path $root "ml")
foreach ($area in @("dupage_central", "cook_suburbs")) {
    Write-Host "--- $area" -ForegroundColor Yellow
    & $venvPython -m forecasting.run --area $area potholes
    if ($LASTEXITCODE -ne 0) { Fail "Pothole reports for $area did not load (SeeClickFix may be busy). Wait 10 minutes and run this again." }
}
Set-Location $root

Step "3/4 Forecasting tests (about 2-5 minutes)"
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "forecast-tests.ps1")

Step "4/4 Backend tests (last: this restarts the backend containers)"
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "backend-tests.ps1")

Write-Host ""
Write-Host "ALL DONE. NOW update the Cloudflare tunnel / restart the backend (scripts\start-live.bat)." -ForegroundColor Green
Write-Host "Then tell Claude 'go live finished'." -ForegroundColor Green
