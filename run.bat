@echo off
chcp 949 >nul 2>&1
title Sourcing Dashboard
echo.
echo ============================================
echo   Sourcing Dashboard Starting...
echo   Browser will open automatically.
echo   Close this window to stop the app.
echo ============================================
echo.
set PYTHON_CMD=
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto found
)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto found
)
python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python3
    goto found
)
echo [ERROR] Python not found. Run install.bat first.
pause
exit /b 1
:found
%PYTHON_CMD% -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Libraries not installed. Run install.bat first.
    pause
    exit /b 1
)
%PYTHON_CMD% -m streamlit run "%~dp0app.py" --server.headless true --browser.gatherUsageStats false
pause
