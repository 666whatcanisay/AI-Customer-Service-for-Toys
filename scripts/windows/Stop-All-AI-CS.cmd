@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-AiCs-CurrentPage.ps1"
echo.
pause
