@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python serveur.py
) else (
  py -3 serveur.py
)
pause
