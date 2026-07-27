@echo off
set /p PILOT_BACKUP_CONFIRM="Type BACKUP to create a local SQLite online backup before planned recovery: "
if /I not "%PILOT_BACKUP_CONFIRM%"=="BACKUP" exit /b 2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup_target_pilot_data.ps1" -ConfirmBackup
pause
