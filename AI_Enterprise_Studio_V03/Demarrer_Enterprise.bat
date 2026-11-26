@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\AIEnterpriseStudio\n8n-token.dpapi" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Lancer_Enterprise.ps1"
) else (
    where py >nul 2>&1
    if errorlevel 1 (python serveur.py) else (py -3 serveur.py)
)
pause
