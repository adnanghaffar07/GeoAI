@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0county-data-check4.ps1" > "%~dp0county-data-check4.log" 2>&1
echo Finished. Log: %~dp0county-data-check4.log
pause
