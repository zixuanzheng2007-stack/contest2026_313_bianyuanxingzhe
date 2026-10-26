@echo off
rem 中文入口：转发到 ASCII 批处理，避免 cmd 找不到文件名
if /i "%~1"=="flash" (
    call "%~dp0EW_MIRROR_FLASH.bat" %2
    exit /b %ERRORLEVEL%
)
call "%~dp0EW_PANEL.bat"
exit /b %ERRORLEVEL%
