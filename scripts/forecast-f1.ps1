# Forecasting F1: download Chicago data, load it into the separate "forecast" database, write the report.
# Start it by double-clicking scripts\forecast-f1.bat. Safe to run again (finished downloads are skipped).
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

Step "3/6 Preparing Python (first time takes a few minutes)"
$python = $null
foreach ($candidate in @("py", "python")) { $found = Get-Command $candidate -ErrorAction SilentlyContinue; if ($found -and $found.Source -notlike "*WindowsApps*") { $python = $candidate; break } }  # skip the Microsoft Store shortcut
if (-not $python) { Fail "Python is not installed. In PowerShell run:  winget install -e --id Python.Python.3.12  then close this window and run this again." }
if (-not (Test-Path "ml\.venv\Scripts\python.exe")) { & $python -m venv ml\.venv; if ($LASTEXITCODE -ne 0) { Fail "Could not create ml\.venv" } }
$venvPython = Join-Path $root "ml\.venv\Scripts\python.exe"
& $venvPython -m pip install --quiet --disable-pip-version-check -r ml\requirements-forecast.txt
if ($LASTEXITCODE -ne 0) { Fail "Could not install the Python packages (check the internet connection)." }

Step "4/6 Chicago data terms"
$termsUrl = "https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html"
Start-Process $termsUrl
Write-Host "The City of Chicago terms page opened in your browser. Please read it."
$answer = Read-Host "Do you accept the Chicago data terms? Type YES to continue"
if ($answer -ne "YES") { Fail "Terms not accepted, nothing downloaded." }

Set-Location (Join-Path $root "ml")
Step "5/6 Downloading (first time about 0.5 GB; new layers add 20-40 minutes)"
& $venvPython -m forecasting.run download --terms-confirmed
if ($LASTEXITCODE -eq 3) { Write-Host "Some downloads failed (listed above). Loading everything else; run this again later to fill the gaps." -ForegroundColor Yellow }
elseif ($LASTEXITCODE -ne 0) { Fail "Download stopped (message above). Run this again later; finished files are kept." }

Step "6/6 Loading into the forecast database and writing the report"
& $venvPython -m forecasting.run load
if ($LASTEXITCODE -ne 0) { Fail "Load stopped (message above)." }
& $venvPython -m forecasting.run report
if ($LASTEXITCODE -ne 0) { Fail "Report stopped (message above)." }

$report = Join-Path $root "ml\forecasting\reports\chicago\f1-data-report.md"
Write-Host ""
Write-Host "ALL DONE. Report: $report" -ForegroundColor Green
Write-Host "Tell Claude 'F1 finished' so it can read the report."
Start-Process notepad.exe $report
