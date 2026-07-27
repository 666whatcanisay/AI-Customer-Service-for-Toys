@echo off
set /p PILOT_RECOVERY_CONFIRM="Type RECOVER to stop A, C, and B one at a time and verify managed recovery: "
if /I not "%PILOT_RECOVERY_CONFIRM%"=="RECOVER" exit /b 2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_target_pilot_component_recovery.ps1" -ConfirmDisruption -AllowFirewallGate
pause
