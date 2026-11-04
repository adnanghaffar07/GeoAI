# P9.5 speed test (about 10-20 minutes). Fills the TEST database (never the app database) with a busy
# year of data, times the main screens and reports, and writes documentation\06-demo\p9-load-report.md.
# Start it by double-clicking scripts\p9-load-test.bat. The log is saved in backend\p9-load-test.log for Claude.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $(Get-Date -Format HH:mm) $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Step "1/3 Starting Docker (database, queue, API, worker)"
if (-not (Select-String -Path ".env" -Pattern '^\s*TEST_DATABASE_URL\s*=' -Quiet)) { Fail "TEST_DATABASE_URL is missing in .env (the speed test only uses the test database)." }
docker compose up -d --wait db queue
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start. Open Docker Desktop, wait until it says 'running', then run this again." }
docker compose up -d api worker beat
if ($LASTEXITCODE -ne 0) { Fail "Docker could not start the API." }

Step "2/3 Filling the test database and timing the screens (about 10-20 minutes; nothing to do meanwhile)"
$log = Join-Path $root "backend\p9-load-test.log"
docker compose exec -T api python -m pytest tests/p9_load.py -s -q -p no:cacheprovider 2>&1 | Tee-Object -FilePath $log
$result = $LASTEXITCODE
docker compose restart worker | Out-Null

Step "3/3 Saving the report"
$report = Join-Path $root "backend\p9-load-report.md"
if (Test-Path $report) {
    Copy-Item $report (Join-Path $root "documentation\06-demo\p9-load-report.md") -Force
    Write-Host "Report saved: documentation\06-demo\p9-load-report.md"
}
if ($result -eq 0) { Write-Host ""; Write-Host "SPEED TEST PASSED: every screen within target. Tell Claude 'speed test finished'." -ForegroundColor Green }
else { Write-Host ""; Write-Host "SPEED TEST FOUND PROBLEMS (above). Tell Claude 'speed test finished': Claude reads backend\p9-load-test.log." -ForegroundColor Yellow }
