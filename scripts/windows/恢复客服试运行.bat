@echo off
set /p TARGET_PILOT_CONFIRM="输入 RESTART 确认安全停止并重新启动客服试运行："
if /I not "%TARGET_PILOT_CONFIRM%"=="RESTART" exit /b 2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0recover_target_pilot.ps1" -ConfirmRestart
pause
