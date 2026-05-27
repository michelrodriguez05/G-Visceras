@echo off
title G-Visceras - Instalacion
cd /d "%~dp0"
echo ========================================
echo   Gestor de Visceras Colbeef - Setup
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python no esta instalado. Instala Python 3.10+ desde python.org
  pause
  exit /b 1
)

if not exist venv (
  echo Creando entorno virtual...
  python -m venv venv
)

call venv\Scripts\activate
echo Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Fallo pip install
  pause
  exit /b 1
)

if not exist .env (
  if exist .env.example copy .env.example .env
  echo Se creo .env desde .env.example
)

if not exist logs mkdir logs
echo.
echo [OK] Instalacion completa.
echo Siguiente paso: ejecutar start.bat
echo.
pause
