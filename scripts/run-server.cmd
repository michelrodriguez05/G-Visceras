@echo off
cd /d "%~dp0.."
if not exist "venv\Scripts\python.exe" (
  echo [ERROR] Ejecuta setup.bat primero.
  exit /b 1
)
if not exist "logs" mkdir logs
set PYTHONUNBUFFERED=1
"venv\Scripts\python.exe" main.py >> "logs\server.log" 2>&1
