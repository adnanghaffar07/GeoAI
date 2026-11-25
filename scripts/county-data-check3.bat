@echo off
rem Evanston pothole count (read-only). Writes scripts\county-data-check3.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0county-data-check3.ps1"
pause
