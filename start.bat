@echo off
title G-Visceras - Iniciar
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Ejecutando setup por primera vez...
  call setup.bat
)

call "%~dp0stop.bat" >nul 2>&1

if not exist logs mkdir logs
echo [%date% %time%] Iniciando servidor...>> logs\server.log

start "G-Visceras Backend" /MIN cmd /c "%~dp0scripts\run-server.cmd"

echo Esperando arranque...
timeout /t 3 /nobreak >nul

curl -s http://127.0.0.1:8000/api/ping >nul 2>&1
if errorlevel 1 (
  echo.
  echo Servidor iniciando en segundo plano...
  echo Si no responde, revisa logs\server.log
) else (
  echo.
  echo [OK] Servidor activo
)

echo.
echo   Local:    http://localhost:8000
echo   Red LAN:  http://%COMPUTERNAME%:8000
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  echo   IP:       http://%%a:8000
)
echo.
echo Para detener:  stop.bat
echo Para reiniciar: restart.bat
echo Log: logs\server.log
echo.
pause
