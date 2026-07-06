@echo off
setlocal
chcp 65001 >nul

set "ROOT_DIR=%~dp0"
set "LAUNCHER=%ROOT_DIR%scripts\teacher-editor.ps1"

echo Chronovita 教师内容编辑器启动器
echo.
echo 将自动启动本地后端 API 和网页编辑器，然后打开：
echo http://127.0.0.1:5173/admin/content
echo.

if not exist "%LAUNCHER%" (
  echo 未找到 "%LAUNCHER%"。
  echo 请确认本文件放在 Chronovita 项目根目录。
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
echo.
echo 如果浏览器没有自动打开，请手动访问：
echo http://127.0.0.1:5173/admin/content
echo.
pause
