@echo off
rem Double-click: prepare the the Cook suburbs research test (roads, weather, SeeClickFix pothole files). See cook-prepare.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cook-prepare.ps1"
echo.
pause
