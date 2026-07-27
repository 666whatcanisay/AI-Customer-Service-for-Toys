@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_target_pilot_readiness.ps1"
pause
