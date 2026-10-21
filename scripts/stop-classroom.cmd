@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%stop-classroom.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Stop failed. Review the message above.
if defined CI exit /b %EXIT_CODE%
pause
exit /b %EXIT_CODE%
