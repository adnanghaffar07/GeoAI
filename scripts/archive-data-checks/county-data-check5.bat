@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0county-data-check5.ps1"
echo.
echo Finished. Log: %~dp0county-data-check5.log
pause
