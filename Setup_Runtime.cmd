@echo off
setlocal
title Fashion Search - Runtime Setup
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 tools\setup_runtime.py
) else (
  python tools\setup_runtime.py
)
if errorlevel 1 (
  echo Setup failed. Read the message above.
  pause
  exit /b 1
)
echo Setup completed. Use Start_Demo.cmd to launch the application.
pause
