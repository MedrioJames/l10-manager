@echo off
title L10 Manager - Setup
echo.
echo   L10 Manager - Setup
echo   Downloading the latest setup from GitHub...
echo.

set "L10_TEMP_INSTALL=%TEMP%\l10-manager-install.ps1"
if exist "%L10_TEMP_INSTALL%" del "%L10_TEMP_INSTALL%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/MedrioJames/l10-manager/main/install.ps1' -OutFile '%L10_TEMP_INSTALL%'"

if not exist "%L10_TEMP_INSTALL%" (
    echo.
    echo   Could not download the setup script. Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%L10_TEMP_INSTALL%"

del "%L10_TEMP_INSTALL%" >nul 2>&1
echo.
pause
