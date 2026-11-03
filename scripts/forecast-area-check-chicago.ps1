# Forecasting any-area step: move Chicago into its own area folders and database schema, then PROVE that Chicago gives
# exactly the same results with the new code, then draft the Level 1 cut-offs from Chicago's training years.
# Start it by double-clicking scripts\forecast-area-check-chicago.bat. About 30-45 minutes. Safe to run again.
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

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

Step "3/6 Backing up the forecast database first (once)"
$backup = Join-Path $root "_backups\forecast-db-before-any-area-2026-10-29.dump"
if (Test-Path $backup) { Write-Host "Backup already there: $backup" }
else {
    docker compose exec -T db pg_dump -U $user -Fc -f /tmp/forecast-before-any-area.dump forecast
    if ($LASTEXITCODE -ne 0) { Fail "The database backup did not work (message above). Nothing was changed." }
    docker compose cp db:/tmp/forecast-before-any-area.dump $backup
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backup)) { Fail "Could not copy the database backup out of Docker. Nothing was changed." }
    Write-Host ("Backup saved: $backup ({0:N0} MB)" -f ((Get-Item $backup).Length / 1MB))
}

$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }
Set-Location (Join-Path $root "ml")

Step "4/6 Moving Chicago into its own folders and database schema (nothing is changed, only moved)"
& $venvPython -m forecasting.run move-to-areas
if ($LASTEXITCODE -ne 0) { Fail "The move stopped (message above). Tell Claude; the backup is in _backups." }

Step "5/6 Same-results check: reload, rebuild and re-score Chicago with the new code (about 30-45 minutes)"
& $venvPython -m forecasting.run same-results-check
$check = $LASTEXITCODE
if ($check -ne 0 -and $check -ne 4) { Fail "The check stopped (message above). Double-click again; tell Claude if it repeats." }

Step "6/6 Drafting the Level 1 risk-factor cut-offs from Chicago's training years"
& $venvPython -m forecasting.run risk-cutoffs-draft
if ($LASTEXITCODE -ne 0) { Fail "Drafting the cut-offs stopped (message above)." }

$report = Join-Path $root "ml\forecasting\reports\chicago\same-results-check.md"
Write-Host ""
if ($check -eq 0) { Write-Host "ALL DONE. Chicago gives the same results. Tell Claude 'Chicago check finished'." -ForegroundColor Green }
else { Write-Host "DONE, BUT SOMETHING DIFFERS (see the report). Tell Claude 'Chicago check finished'." -ForegroundColor Yellow }
Start-Process notepad.exe $report
