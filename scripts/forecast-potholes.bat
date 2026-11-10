@echo off
rem Double-click: a city's own pothole reports (Naperville), nothing else touched (see forecast-potholes.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-potholes.ps1"
echo.
pause
