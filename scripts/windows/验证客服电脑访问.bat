@echo off
set /p PILOT_SERVER_HOST="Enter the server private IPv4 shown by the pilot readiness check: "
if "%PILOT_SERVER_HOST%"=="" exit /b 2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_customer_pilot_access.ps1" -ServerHost "%PILOT_SERVER_HOST%" -Port 5173
pause
