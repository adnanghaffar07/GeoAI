@echo off
rem County expansion part 2 (read-only): Aurora pothole counts by year, and Evanston's ArcGIS 311 data. Writes scripts\county-data-check2.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0county-data-check2.ps1"
pause
