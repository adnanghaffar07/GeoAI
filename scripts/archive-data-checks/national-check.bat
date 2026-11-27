@echo off
rem Double-click: read-only check of the free US-wide data (see national-check.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0national-check.ps1"
echo.
pause
