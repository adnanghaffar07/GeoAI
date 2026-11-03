@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0frontend-tests.ps1"
pause
