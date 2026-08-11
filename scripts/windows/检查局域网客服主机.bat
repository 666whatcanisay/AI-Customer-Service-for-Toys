@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Get-ChannelAgentLanHostStatus.ps1"
pause
exit /b %errorlevel%
