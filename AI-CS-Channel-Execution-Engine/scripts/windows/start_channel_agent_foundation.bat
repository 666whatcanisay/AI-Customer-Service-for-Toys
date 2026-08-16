@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
set "CONFIG_PATH=%REPO_ROOT%\deploy\channel-agent-foundation\agent.example.json"

if not "%~1"=="" set "CONFIG_PATH=%~f1"

if exist "%REPO_ROOT%\dist\channel-agent.exe" (
  "%REPO_ROOT%\dist\channel-agent.exe" run --config "%CONFIG_PATH%"
  exit /b %ERRORLEVEL%
)

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
  set "PYTHONPATH=%REPO_ROOT%\src"
  "%REPO_ROOT%\.venv\Scripts\python.exe" -m channel_agent run --config "%CONFIG_PATH%"
  exit /b %ERRORLEVEL%
)

set "PYTHONPATH=%REPO_ROOT%\src"
python -m channel_agent run --config "%CONFIG_PATH%"
exit /b %ERRORLEVEL%
