@echo off
setlocal
set "ROOT_DIR=%~dp0.."
if "%~1"=="" (
  echo Usage: install-shiji-facsimile.cmd path-to-zip
  exit /b 2
)
"%ROOT_DIR%\.venv\Scripts\python.exe" "%ROOT_DIR%\scripts\install_shiji_facsimile.py" --archive "%~1"
exit /b %ERRORLEVEL%
