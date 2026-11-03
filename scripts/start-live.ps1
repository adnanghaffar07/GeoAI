# Live demo: live settings, start Docker, start the Cloudflare tunnel, put its address in frontend\vercel.json.
# Double-click scripts\start-live.bat. Then push to GitHub (commands are printed at the end).
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

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) { Fail "cloudflared is not installed or not on PATH." }
Step "Live-demo settings in .env"
Set-EnvLine "PUBLIC_APP_URL" "https://geo-ai-liart.vercel.app"
Set-EnvLine "SESSION_COOKIE_SECURE" "true"
Start-App
Step "Starting the Cloudflare tunnel (runs in the background, minimized)"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
$log = Join-Path $root "_backups\cloudflared.log"
if (Test-Path $log) { Remove-Item $log }
Start-Process -FilePath "cloudflared" -ArgumentList "tunnel --url http://localhost:8000" -RedirectStandardError $log -WindowStyle Minimized | Out-Null
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $log) {
        $found = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches | ForEach-Object { $_.Matches.Value } | Where-Object { $_ -notmatch "//api\." } | Select-Object -First 1
        if ($found) { $url = $found }
    }
}
if (-not $url) { Fail "The tunnel did not give an address within 2 minutes. See $log" }
Write-Host "Tunnel address: $url" -ForegroundColor Green
Step "Writing the address into frontend\vercel.json"
$vercel = Join-Path $root "frontend\vercel.json"
$text = Get-Content $vercel -Raw
$text = $text -replace "https://[a-z0-9-]+\.trycloudflare\.com", $url
Set-Content $vercel $text -NoNewline -Encoding ascii
Step "Checking the backend through the tunnel"
Start-Sleep -Seconds 5
try { $h = Invoke-WebRequest -UseBasicParsing "$url/api/health" -TimeoutSec 30; Write-Host "Health check: $($h.StatusCode)" -ForegroundColor Green } catch { Write-Host "Health check did not answer yet (new tunnels can take a minute). Try $url/api/health in the browser." -ForegroundColor Yellow }
Write-Host ""
Write-Host "READY. Keep this computer on; the tunnel runs in the background (stop it with: Stop-Process -Name cloudflared)." -ForegroundColor Green
Write-Host "Now push to GitHub so Vercel uses the new address:" -ForegroundColor Green
Write-Host "  git status"
Write-Host "  git add -A"
Write-Host "  git commit -m ""Update tunnel address"""
Write-Host "  git push origin development"
