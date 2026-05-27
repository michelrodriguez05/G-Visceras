@echo off
title G-Visceras - Consola (depuracion)
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" call setup.bat
call stop.bat >nul 2>&1
echo Iniciando con ventana visible. Ctrl+C para detener.
echo http://localhost:8000
echo.
call venv\Scripts\activate
python main.py
