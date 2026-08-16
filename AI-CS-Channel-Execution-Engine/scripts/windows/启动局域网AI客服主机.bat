@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0Start-ChannelAgentLanHost.ps1""'; exit $p.ExitCode"
if errorlevel 1 pause
exit /b %errorlevel%
