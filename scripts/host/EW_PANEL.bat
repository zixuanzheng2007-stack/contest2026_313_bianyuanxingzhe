@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "ROOT=%CD%"
set "HOST=%~dp0"
set "PANEL=%ROOT%\tools\ew_panel.py"
set "LAUNCHER=%HOST%EW_PANEL.ps1"
set "PSH=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%PANEL%" goto :missing_panel
if not exist "%LAUNCHER%" goto :missing_launcher
if not exist "%PSH%" goto :missing_psh

echo.
echo Edge Walker DevKit Panel
echo ------------------------
echo Port   COM7 @ 1000000
echo Mirror + serial remote control
echo Log    VMware_share\artifacts\ew_panel_*.log
echo.
echo Close sscom / PuTTY before start.
echo.

"%PSH%" -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" goto :failed

echo.
echo Panel started. Run this bat again to bring window to front.
ping 127.0.0.1 -n 3 >nul
exit /b 0

:missing_panel
echo [ERROR] missing %PANEL%
pause
exit /b 1

:missing_launcher
echo [ERROR] missing %LAUNCHER%
pause
exit /b 1

:missing_psh
echo [ERROR] missing PowerShell: %PSH%
pause
exit /b 1

:failed
echo.
echo [ERROR] start failed, exit=%EC%
echo Try: set EW_PANEL_PYTHON=D:\anaconda3\python.exe
pause
exit /b %EC%
