@echo off
setlocal
title Fashion Search - Graduation Presentation
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The project virtual environment is missing.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -u "tools\launch_demo.py"
if errorlevel 1 (
  echo Startup failed. Read the message above.
  pause
  exit /b 1
)
