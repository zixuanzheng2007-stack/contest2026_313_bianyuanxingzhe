@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Edge Walker - flash + ew_panel

rem Usage: EW_MIRROR_FLASH.bat [COM port, default COM7]

cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM7"
set "FW=%ROOT%\VMware_share\artifacts\nuttx_wifiui.bin"
set "FLASH_PS1=%ROOT%\scripts\host\flash_sf32.ps1"

echo.
echo === Flash mirror firmware (%PORT%) ===
if not exist "%FW%" (
    echo [ERROR] Firmware not found: %FW%
    echo Build in VM: VMware_share\scripts\run_ew_wifiui_build.sh
    goto end_fail
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%FLASH_PS1%" -Port %PORT% -Firmware "%FW%@0x12010000"
if errorlevel 1 (
    echo [ERROR] Flash failed. Check COM port and sftool.
    goto end_fail
)

echo Flash OK. Opening panel in 2s...
timeout /t 2 /nobreak >nul
call "%~dp0EW_PANEL.bat"
exit /b %ERRORLEVEL%

:end_fail
pause
exit /b 1
