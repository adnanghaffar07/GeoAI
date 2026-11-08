@echo off
rem Double-click: HPMS road condition for one area (see forecast-hpms.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-hpms.ps1"
echo.
pause
