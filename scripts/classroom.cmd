@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "SKIP_PAUSE="
for %%A in (%*) do if /I "%%~A"=="-SkipBrowser" set "SKIP_PAUSE=1"
set "PSModulePath="
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%classroom.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Classroom launch failed. Review .chronovita-classroom\logs.
if defined CI exit /b %EXIT_CODE%
if defined SKIP_PAUSE exit /b %EXIT_CODE%
pause
exit /b %EXIT_CODE%
