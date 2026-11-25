@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0county-data-download.ps1"
echo.
echo Finished. Files are in %~dp0seeclickfix-data
pause
