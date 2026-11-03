# One-time: download the free assistant model (about 0.4 GB) for "Ask about road risk" (CR-006).
# Double-click scripts\assistant-model.bat. Needs internet once; afterwards the model stays on this computer.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose up -d ollama
if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED: Docker could not start the assistant container." -ForegroundColor Red; exit 1 }
Write-Host "Downloading qwen2.5:0.5b (about 0.4 GB). On a slow connection this can take 1-2 hours..." -ForegroundColor Cyan
docker compose exec -T ollama ollama pull qwen2.5:0.5b
if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED: the download did not finish. Run this again; it continues." -ForegroundColor Red; exit 1 }
docker compose exec -T ollama ollama list
Write-Host "ASSISTANT MODEL READY." -ForegroundColor Green
