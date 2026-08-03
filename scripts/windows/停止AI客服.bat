@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_ai_customer_service.ps1" %*
set "AI_CS_EXIT_CODE=%ERRORLEVEL%"
if not "%AI_CS_EXIT_CODE%"=="0" echo [错误] AI-CS 停止失败，退出码：%AI_CS_EXIT_CODE%
pause
exit /b %AI_CS_EXIT_CODE%
