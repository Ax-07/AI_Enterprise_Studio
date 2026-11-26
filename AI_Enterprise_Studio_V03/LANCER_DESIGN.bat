@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python preview_campus.py --original
) else (
  py -3 preview_campus.py --original
)
pause
