@echo off
rem Double-click: prepare the the Aurora research test (roads, weather, SeeClickFix pothole files). See aurora-prepare.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aurora-prepare.ps1"
echo.
pause
