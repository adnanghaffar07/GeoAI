@echo off
rem Double-click to run backend-tests.ps1 (see the first lines of that file).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backend-tests.ps1"
echo.
pause
