@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Stop-PortableProject.ps1" -IncludeCurrentPageAgent
if errorlevel 1 pause
