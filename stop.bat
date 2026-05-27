@echo off
title G-Visceras - Detener
cd /d "%~dp0"
echo Deteniendo Gestor de Visceras...

set KILLED=0
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo Cerrando proceso PID %%p en puerto 8000...
  taskkill /PID %%p /F >nul 2>&1
  set KILLED=1
)

taskkill /FI "WINDOWTITLE eq G-Visceras Backend*" /F >nul 2>&1

if "%KILLED%"=="1" (
  echo [OK] Servidor detenido.
) else (
  echo No habia servidor escuchando en puerto 8000.
)
