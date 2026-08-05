@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ai_cs_server.ps1" %*
exit /b %errorlevel%
