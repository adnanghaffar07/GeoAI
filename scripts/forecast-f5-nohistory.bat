@echo off
rem Double-click to run the F5 no-history experiment (about 10-30 minutes).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-f5-nohistory.ps1"
echo.
pause
