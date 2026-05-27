@echo off
title G-Visceras - Estado
cd /d "%~dp0"
echo === Estado del servidor ===
echo.
netstat -ano | findstr ":8000" | findstr "LISTENING"
if errorlevel 1 (
  echo Puerto 8000: NO activo
) else (
  echo Puerto 8000: ACTIVO
  curl -s http://127.0.0.1:8000/api/ping 2>nul
  echo.
)
echo.
if exist logs\server.log (
  echo --- Ultimas 15 lineas del log ---
  powershell -Command "Get-Content 'logs\server.log' -Tail 15"
) else (
  echo Sin archivo de log aun.
)
echo.
pause
