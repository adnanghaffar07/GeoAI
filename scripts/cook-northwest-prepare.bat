@echo off
rem Double-click: prepare the the Cook northwest research test (roads, weather, SeeClickFix pothole files). See cook-northwest-prepare.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cook-northwest-prepare.ps1"
echo.
pause
