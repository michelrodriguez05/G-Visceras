@echo off
title G-Visceras - Autoarranque Windows
cd /d "%~dp0"
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LINK=%STARTUP%\G-Visceras-Iniciar.lnk
set TARGET=%~dp0start.bat

echo Creando acceso directo en inicio de Windows...
echo Destino: %TARGET%

powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut('%LINK%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Description='Gestor Visceras Colbeef'; $s.Save()"

if exist "%LINK%" (
  echo.
  echo [OK] Autoarranque instalado.
  echo El servidor iniciara al iniciar sesion en Windows.
  echo Para quitar: uninstall-autostart.bat
) else (
  echo [ERROR] No se pudo crear el acceso directo.
)
echo.
pause
