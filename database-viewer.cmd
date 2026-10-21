@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PYTHON_EXE="
if exist "%ROOT_DIR%.venv\Scripts\pythonw.exe" set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\pythonw.exe"
if not defined PYTHON_EXE if exist "%ROOT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python313\pythonw.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\pythonw.exe"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python312\pythonw.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\pythonw.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

start "Chronovita Database Viewer" "%PYTHON_EXE%" "%ROOT_DIR%scripts\database_viewer.py" %*
exit /b 0
