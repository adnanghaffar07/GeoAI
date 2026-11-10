@echo off
rem Double-click: download a city's pothole history again and reload it (see forecast-city-refresh.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-city-refresh.ps1"
echo.
pause
