@echo off
title G-Visceras - Reiniciar
cd /d "%~dp0"
echo ========================================
echo   Reiniciando backend G-Visceras
echo ========================================
echo.
call "%~dp0stop.bat"
timeout /t 2 /nobreak >nul
call "%~dp0start.bat"
