@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "LAUNCHER=%ROOT_DIR%scripts\teacher-editor.ps1"

echo Chronovita teacher editor launcher
echo.
echo This will start the local API and web editor, then open:
echo http://127.0.0.1:5173/admin/content
echo.

if not exist "%LAUNCHER%" (
  echo Cannot find "%LAUNCHER%".
  echo Please keep this file in the Chronovita project root.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo Launch failed. Please send the error text or the .teacher-editor-logs folder to the developer team.
  echo.
  pause
  exit /b %EXIT_CODE%
)
echo If the browser did not open, visit:
echo http://127.0.0.1:5173/admin/content
echo.
pause
