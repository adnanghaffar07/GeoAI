@echo off
rem Item 10 check (read-only): IDOT Gateway cameras near Naperville. Writes scripts\camera-check.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0camera-check.ps1"
pause
