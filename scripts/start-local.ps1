# Test on this laptop: local settings, start Docker, open the screens at http://localhost:5173.
# Double-click scripts\start-local.bat. Close the window (or Ctrl+C) to stop the screens; Docker keeps running.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Step($text) { Write-Host ""; Write-Host "==> $(Get-Date -Format HH:mm) $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }
function Set-EnvLine($name, $value) {
    $lines = Get-Content ".env"
    if ($lines -match "^\s*$name\s*=") { $lines = $lines -replace "^\s*$name\s*=.*$", "$name=$value" } else { $lines += "$name=$value" }
    Set-Content ".env" $lines -Encoding ascii
}
if (-not (Test-Path ".env")) { Fail "No .env file in $root" }
if (-not (Test-Path ".env.backup-live-demo")) { Copy-Item ".env" ".env.backup-live-demo"; Write-Host "Saved a copy of .env as .env.backup-live-demo" }
function Start-App {
    Step "Starting Docker (database, queue, API, worker, scheduler)"
    docker compose up -d --wait db queue
    if ($LASTEXITCODE -ne 0) { Fail "Docker did not start. Open Docker Desktop, wait for 'Engine running', then run this again." }
    docker compose up -d api worker beat ollama
    if ($LASTEXITCODE -ne 0) { Fail "Docker could not start the app (message above)." }
    docker compose exec -T api alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail "The database update stopped (message above). Tell Claude." }
    docker compose ps
}

Step "Local settings in .env (sign-in at http://localhost:5173)"
Set-EnvLine "PUBLIC_APP_URL" "http://localhost:5173"
Set-EnvLine "SESSION_COOKIE_SECURE" "false"
Start-App
Step "Starting the screens. Open http://localhost:5173 in your browser and sign in. Keep this window open."
$busy = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($busy) { Write-Host "Closing the old copy of the screens on port 5173"; $busy | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Start-Sleep -Seconds 2 }
Set-Location (Join-Path $root "frontend")
npm run dev -- --port 5173 --strictPort
