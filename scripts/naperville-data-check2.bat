@echo off
rem Naperville focus, check 2 (read-only). Writes scripts\naperville-data-check2.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0naperville-data-check2.ps1"
pause
