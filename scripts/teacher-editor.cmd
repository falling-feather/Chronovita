@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%teacher-editor.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo Launch failed. Review the message above and the .teacher-editor-logs folder.
)
if defined CI exit /b %EXIT_CODE%
pause
exit /b %EXIT_CODE%
