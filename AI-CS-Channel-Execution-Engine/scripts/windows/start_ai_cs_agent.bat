@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "AGENT_HOME=%~dp0.."
set "AGENT_APP=%AGENT_HOME%\exe\ai-cs-agent.pyz"
set "AGENT_CONFIG=%AGENT_HOME%\config\agent.json"

if not exist "%AGENT_APP%" (
  echo AI-CS Agent 启动文件缺失：%AGENT_APP%
  exit /b 4
)

set "AGENT_PYTHON="
if exist "%AGENT_HOME%\exe\python.exe" (
  set "PYTHONHOME=%AGENT_HOME%\runtime\python"
  set "PYTHONNOUSERSITE=1"
  set "PYTHONUTF8=1"
  set AGENT_PYTHON="%AGENT_HOME%\exe\python.exe"
)
if not defined AGENT_PYTHON (
  py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>nul
  if not errorlevel 1 set "AGENT_PYTHON=py -3.12"
)
if not defined AGENT_PYTHON (
  python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>nul
  if not errorlevel 1 set "AGENT_PYTHON=python"
)
if not defined AGENT_PYTHON (
  echo AI-CS Agent 内置 Python 不可用，请重新安装发布包。
  exit /b 4
)

if "%~1"=="" (
  echo 用法：start_ai_cs_agent.bat configure^|start^|status^|stop^|kill-switch enable^|disable
  exit /b 1
)

if /I "%~1"=="start" if not exist "%AGENT_CONFIG%" (
  echo 首次启动需要完成安全配置。
  call %AGENT_PYTHON% "%AGENT_APP%" configure --home "%AGENT_HOME%" --config "%AGENT_CONFIG%"
  set "AGENT_EXIT_CODE=!ERRORLEVEL!"
  if not "!AGENT_EXIT_CODE!"=="0" exit /b !AGENT_EXIT_CODE!
)

call %AGENT_PYTHON% "%AGENT_APP%" %* --home "%AGENT_HOME%" --config "%AGENT_CONFIG%"
set "AGENT_EXIT_CODE=%ERRORLEVEL%"
exit /b %AGENT_EXIT_CODE%
