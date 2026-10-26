@echo off
setlocal EnableExtensions
chcp 65001 >nul
title TASK_031 flash nuttx_wifi_scan_ui.bin

cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM7"
set "BIN=%ROOT%\VMware_share\artifacts\nuttx_wifi_scan_ui.bin"
set "SFT=%ROOT%\tools\sftool\sftool.exe"

if not exist "%BIN%" (
    echo [ERROR] Missing %BIN%
    pause & exit /b 1
)
if not exist "%SFT%" (
    echo [ERROR] Missing sftool.exe
    pause & exit /b 1
)

echo Flash %BIN% to %PORT% @ 0x12010000 ...
"%SFT%" -c SF32LB52 -p %PORT% --baud 1000000 write_flash --verify "%BIN%@0x12010000"
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo [ERROR] flash exit %EC%
    pause & exit /b %EC%
)

echo.
echo Flash OK. Close sscom/ew_panel, then run:
echo   python scripts\host\task031_accept.py
timeout /t 3 /nobreak >nul
exit /b 0
