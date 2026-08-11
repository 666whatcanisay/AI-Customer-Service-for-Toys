@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\Install-AI-CS-Channel-Agent.ps1" -PackageRoot "%~dp0" -CreateShortcuts -Launch
if errorlevel 1 (
  echo 安装失败，请把本窗口中的错误信息交给管理员。
  pause
)
exit /b %errorlevel%
