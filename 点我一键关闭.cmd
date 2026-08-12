@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "STOPPER_PS1=%ROOT_DIR%scripts\stop-teacher-editor.ps1"
set "STOPPER_CMD=%ROOT_DIR%scripts\stop-teacher-editor.cmd"

echo Chronovita teacher editor stopper
echo.
echo This will stop the local API and web editor.
echo Drafts and local credentials will not be removed.
echo.

if exist "%STOPPER_PS1%" goto run_powershell
if exist "%STOPPER_CMD%" goto run_legacy_cmd

echo Cannot find the Chronovita stop helper.
echo Keep this file in the extracted package root and try again.
echo.
pause
exit /b 1

:run_powershell
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%STOPPER_PS1%" %*
set "EXIT_CODE=%ERRORLEVEL%"
goto finish

:run_legacy_cmd
set "PSModulePath="
call "%STOPPER_CMD%" %*
exit /b %ERRORLEVEL%

:finish
echo.
if not "%EXIT_CODE%"=="0" (
  echo Stop failed. Review the message above.
  echo.
) else (
  echo Chronovita local services are closed.
  echo.
)
if defined CI exit /b %EXIT_CODE%
pause
exit /b %EXIT_CODE%
