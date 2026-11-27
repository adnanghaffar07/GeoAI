@echo off
rem County expansion (read-only): checks Aurora (Kane/DuPage/Will/Kendall) and Evanston (Cook) pothole data. Writes scripts\county-data-check.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0county-data-check.ps1"
pause
