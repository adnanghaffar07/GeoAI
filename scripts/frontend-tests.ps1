# Frontend: type check, lint and all screen tests (about 1-3 minutes).
# Start it by double-clicking scripts\frontend-tests.bat. Results are saved in frontend\frontend-tests.log for Claude.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "frontend")
$log = Join-Path $root "frontend\frontend-tests.log"
function Step($text) { Write-Host ""; Write-Host "==> $(Get-Date -Format HH:mm) $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; Write-Host "Send Claude the file $log"; exit 1 }

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "npm (Node.js) is not installed or not on PATH." }
"Frontend tests $(Get-Date)" | Out-File $log -Encoding utf8

Step "1/3 Type check"
npm run typecheck 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Fail "The type check found problems (above)." }

Step "2/3 Lint"
npm run lint 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Fail "The lint check found problems (above)." }

Step "3/3 Screen tests"
npm test 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Fail "Some screen tests failed (above)." }

Write-Host ""
Write-Host "ALL FRONTEND TESTS PASSED. Tell Claude 'frontend tests finished'." -ForegroundColor Green
