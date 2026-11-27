@echo off
rem Double-click: step-by-step check of HPMS 2024 for Illinois (see hpms-table-check.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0hpms-table-check.ps1"
echo.
pause
