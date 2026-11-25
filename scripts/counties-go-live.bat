@echo off
rem Double-click: reload DuPage + Cook pothole reports, run all tests, backend tests last (see counties-go-live.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0counties-go-live.ps1"
echo.
pause
