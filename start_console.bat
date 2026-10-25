@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow README.md to create .venv and install requirements first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" src\web_console.py --host 127.0.0.1 --port 8001
pause
