@echo off
rem Double-click to run the F2 LOCKED TEST (once, after the owner go-ahead).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-f2-test.ps1"
echo.
pause
