# Forecasting F2: the LOCKED TEST. Runs ONCE, only after the owner has read the validation report with Claude.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Write-Host "This runs the LOCKED TEST (July 2022 - June 2025). It can be run only ONCE, ever." -ForegroundColor Yellow
Write-Host "Run it only after reading the validation report with Claude and agreeing to go ahead." -ForegroundColor Yellow
$answer = Read-Host "Type RUN THE TEST to continue"
if ($answer -ne "RUN THE TEST") { Fail "Not confirmed. Nothing was run." }
do {
    $choice = (Read-Host "Main model: type 1 for WITH traffic or 2 for WITHOUT traffic, as agreed with Claude").Trim()
    if ($choice -ne "1" -and $choice -ne "2") { Write-Host "Please type only the number 1 or 2." -ForegroundColor Yellow }
} until ($choice -eq "1" -or $choice -eq "2")
$mainModel = if ($choice -eq "2") { "without_traffic" } else { "with_traffic" }

$envFile = @{}
Get-Content ".env" | ForEach-Object { if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') } }
$env:FORECAST_DATABASE_URL = "postgresql://" + [uri]::EscapeDataString($envFile["POSTGRES_USER"]) + ":" + [uri]::EscapeDataString($envFile["POSTGRES_PASSWORD"]) + "@127.0.0.1:5432/forecast"

Step "Starting the database in Docker"
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Fail "Docker did not start the database. Open Docker Desktop, then run this again (the test has not started)." }

Set-Location (Join-Path $root "ml")
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
Step "Running the locked test with the $mainModel main model (about 10-20 minutes)"
& $venvPython -m forecasting.run f2-test --owner-go-ahead --main-model $mainModel
if ($LASTEXITCODE -ne 0) { Fail "The locked test stopped (message above). Double-click again (same main model) to continue; send the message to Claude if it repeats." }

$report = Join-Path $root "ml\forecasting\reports\chicago\f2-test-report.md"
Write-Host ""
Write-Host "ALL DONE. Test report: $report" -ForegroundColor Green
Write-Host "Tell Claude 'F2 test finished'."
Start-Process notepad.exe $report
