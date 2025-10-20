@echo off

REM Usage: ...geah/> system/launch_service "python hl7_app/hl7service.py"

REM Check if an argument (command) is provided
if "%~1"=="" (
    echo Please provide a command to execute.
    exit /b
)

:loop

REM Execute the provided command
echo Launch service
%~1

REM Set the time interval (in seconds) between executions
timeout /t 5 >nul

REM Repeat the loop
goto loop
