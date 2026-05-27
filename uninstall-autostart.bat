@echo off
set LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\G-Visceras-Iniciar.lnk
if exist "%LINK%" (
  del "%LINK%"
  echo [OK] Autoarranque eliminado.
) else (
  echo No habia acceso directo de autoarranque.
)
pause
