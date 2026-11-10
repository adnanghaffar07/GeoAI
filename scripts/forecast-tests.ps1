# Forecasting: run ALL forecasting tests on this laptop, including the database tests (in a separate test database
# "forecast_test" that the tests may empty; the real "forecast" database is never touched).
# Start it by double-clicking scripts\forecast-tests.bat. The results are saved in ml\forecast-tests.log for Claude.
$ErrorActionPreference = "Continue"   # native tools write progress to stderr; we check exit codes instead
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Step "1/4 Reading database user and password from .env"
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$user = $envFile["POSTGRES_USER"]; $password = $envFile["POSTGRES_PASSWORD"]
if (-not $user -or -not $password) { Fail "POSTGRES_USER or POSTGRES_PASSWORD missing in .env" }
$env:FORECAST_TEST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($user) + ":" + [uri]::EscapeDataString($password) + "@127.0.0.1:5432/forecast_test"
Write-Host "OK (test database 'forecast_test')"

Step "2/4 Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, wait until it says 'running', then run this again." }

Step "3/4 Preparing Python (installs pytest the first time)"
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) { Fail "ml\.venv is missing. Run scripts\forecast-f1.bat first." }
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt pytest pytest-timeout
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }

Set-Location (Join-Path $root "ml")
Step "4/4 Running the forecasting tests (about 2-5 minutes; each test name is shown as it runs)"
$log = Join-Path $root "ml\forecast-tests.log"
$env:PYTHONUNBUFFERED = "1"
& $venvPython -u -m pytest tests\test_forecast_areas.py tests\test_forecast_download.py tests\test_forecast_load.py tests\test_forecast_f2.py tests\test_forecast_sections.py tests\test_forecast_live.py tests\test_forecast_hpms.py tests\test_forecast_cities.py tests\test_forecast_transfer.py -v -rs --durations=10 --timeout=240 -p no:cacheprovider 2>&1 | Tee-Object -FilePath $log
$result = $LASTEXITCODE
if ($result -eq 0) { Write-Host ""; Write-Host "ALL TESTS PASSED. Tell Claude 'tests finished'." -ForegroundColor Green }
else { Write-Host "SOME TESTS FAILED (list above). Tell Claude 'tests finished': Claude reads ml\forecast-tests.log." -ForegroundColor Yellow }
