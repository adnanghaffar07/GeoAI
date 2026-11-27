@echo off
rem Double-click to run the F6 county-model experiment (about 30-90 minutes the first time).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-f6-county-model.ps1"
echo.
pause
