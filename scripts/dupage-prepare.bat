@echo off
rem Double-click: prepare the Central DuPage research test (roads, weather, SeeClickFix pothole files). See dupage-prepare.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dupage-prepare.ps1"
echo.
pause
