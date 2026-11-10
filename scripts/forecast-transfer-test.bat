@echo off
rem Double-click: locked transfer test of the Chicago model on Naperville (see forecast-transfer-test.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0forecast-transfer-test.ps1"
echo.
pause
