# Backend: apply the new database migration and run ALL backend tests (about 2-5 minutes).
# Backs up the app database once before each new migration (0009 forecasting tables, 0010 road-risk screens).
# Start it by double-clicking scripts\backend-tests.bat. Results are saved in backend\backend-tests.log for Claude.
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $(Get-Date -Format HH:mm) $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Step "1/5 Reading the database settings from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $appDb = $envFile["POSTGRES_DB"]
if (-not $user -or -not $appDb) { Fail "POSTGRES_USER or POSTGRES_DB missing in .env" }
if (-not $envFile["TEST_DATABASE_URL"]) { Write-Host "Note: TEST_DATABASE_URL is not in .env, so the database tests will be skipped (see .env.example)." -ForegroundColor Yellow }

Step "2/5 Starting the database and the queue in Docker"
docker compose up -d --wait db queue
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start. Open Docker Desktop, wait until it says 'running', then run this again." }

Step "3/5 Backing up the app database (once per new migration; now before 0013 and 0014 (agreements, own storage))"
$backup = Join-Path $root "_backups\app-db-before-0013-user-agreements.dump"
if (Test-Path $backup) { Write-Host "Backup already there: $backup" }
else {
    docker compose exec -T db pg_dump -U $user -Fc -f /tmp/app-before-0013.dump $appDb
    if ($LASTEXITCODE -ne 0) { Fail "The app database backup did not work (message above). Nothing was changed." }
    docker compose cp db:/tmp/app-before-0013.dump $backup
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backup)) { Fail "Could not copy the backup out of Docker. Nothing was changed." }
    Write-Host ("Backup saved: $backup ({0:N1} MB)" -f ((Get-Item $backup).Length / 1MB))
}

Step "4/5 Building the app image if needed (first time after a change: about 5-10 minutes), starting the API, worker and scheduler, applying migrations"
docker compose build api worker beat
if ($LASTEXITCODE -ne 0) { Fail "Docker could not build the app image (message above). Check the internet connection and run this again." }
docker compose up -d api worker beat
if ($LASTEXITCODE -ne 0) { Fail "Docker could not start the API." }
docker compose exec -T api alembic upgrade head
if ($LASTEXITCODE -ne 0) { Fail "The migration stopped (message above). The backup is in _backups; tell Claude." }
docker compose exec -T api alembic current

Step "5/5 Running all backend tests (about 2-5 minutes)"
$log = Join-Path $root "backend\backend-tests.log"
docker compose exec -T api python -m pytest -q -rs -p no:cacheprovider 2>&1 | Tee-Object -FilePath $log
$result = $LASTEXITCODE
docker compose restart worker | Out-Null
if ($result -eq 0) { Write-Host ""; Write-Host "ALL BACKEND TESTS PASSED. Tell Claude 'backend tests finished'." -ForegroundColor Green }
else { Write-Host "SOME TESTS FAILED (list above). Tell Claude 'backend tests finished': Claude reads backend\backend-tests.log." -ForegroundColor Yellow }
