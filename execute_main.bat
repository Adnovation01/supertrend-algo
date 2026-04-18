@echo off

REM Create virtual environment.
echo Creating virtual environment.
python -m venv venv

REM Activate virtual environment.
echo Activating virtual environment.
call venv\Scripts\activate.bat

REM Install packages from requirements.txt
echo Installing Python packages.
call venv\Scripts\python.exe -m pip install -r requirements.txt
echo Python packages installed.

REM Start the Flask backend server
echo Starting Flask backend server
start cmd /k call venv\Scripts\python.exe main.py
