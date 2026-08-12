@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "LAUNCHER=%ROOT_DIR%scripts\teacher-editor.ps1"
set "SKIP_PAUSE="
for %%A in (%*) do if /I "%%~A"=="-SkipBrowser" set "SKIP_PAUSE=1"

echo Chronovita teacher editor launcher
echo.
echo This will start the local API and web editor, then open:
echo http://127.0.0.1:5173/admin/content
echo.

if not exist "%LAUNCHER%" (
  echo Cannot find "%LAUNCHER%".
  echo Please keep this file in the Chronovita project root.
  echo.
  if not defined CI if not defined SKIP_PAUSE pause
  exit /b 1
)

set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo Launch failed. Please send the error text or the .teacher-editor-logs folder to the developer team.
  echo.
) else (
  echo If the browser did not open, visit:
  echo http://127.0.0.1:5173/admin/content
  echo.
)
if defined CI exit /b %EXIT_CODE%
if defined SKIP_PAUSE exit /b %EXIT_CODE%
pause
exit /b %EXIT_CODE%
