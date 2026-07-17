@echo off
title L10 Manager - Setup
echo.
echo   L10 Manager - Setup
echo   Fetching the latest setup from GitHub...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/MedrioJames/l10-manager/main/install.ps1 | iex"
echo.
pause
