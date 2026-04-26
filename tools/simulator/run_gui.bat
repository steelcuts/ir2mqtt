@echo off
rem This script sets up a virtual environment and runs the PyQt simulator GUI.

rem Change to the script's directory
cd /d "%~dp0"

set VENV_DIR=venv

rem Check if the virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment. Please make sure python and venv are installed and in your PATH.
        pause
        exit /b 1
    )
)

rem Activate the virtual environment and install dependencies
call "%VENV_DIR%\Scripts\activate.bat"
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies from requirements.txt. Please check for errors.
    pause
    exit /b %errorlevel%
)

rem Run the application
echo Starting PyQt Simulator GUI...
python simulator_gui.py

rem Deactivate the virtual environment
call deactivate
