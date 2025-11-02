::echo off
@echo off

REM Check if the script is already running with administrative privileges
NET SESSION >nul 2>&1
if %errorLevel% == 0 (
    REM The script is already running with administrative privileges
    goto :main
) else (
    REM Request elevation to run the script with administrator privileges
    powershell -Command "Start-Process '%comspec%' -ArgumentList '/c %~0' -Verb RunAs"
    exit /b
)

:main
setlocal

if exist "%windir%\sysnative\pnputil.exe" (
    %windir%\sysnative\pnputil.exe -i -a  %0\..\STM32Bootloader.inf
) else (
    pnputil -i -a  %0\..\STM32Bootloader.inf
)


endlocal
pause Press any key to exit...
exit

