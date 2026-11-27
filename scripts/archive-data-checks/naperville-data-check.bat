@echo off
rem Naperville focus (read-only): checks the city's open data portal. Writes scripts\naperville-data-check.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0naperville-data-check.ps1"
pause
