@echo off
chcp 949 >nul 2>&1
title Sourcing Dashboard - Install
echo.
echo ============================================
echo   Sourcing Dashboard - Install
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
echo.
echo [ERROR] Python not found!
echo.
echo  1. Go to https://python.org
echo  2. Click Download Python
echo  3. Check 'Add Python to PATH' and Install
echo.
pause
exit /b 1
:found
echo [OK] Python found: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.
echo Installing libraries... (2-3 min)
echo.
%PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Install failed.
    pause
    exit /b 1
)
echo.
echo ============================================
echo =                                          =
echo =         Install Complete!                =
echo =                                          =
echo =    Now double-click run.bat              =
echo =                                          =
echo ============================================
echo.
pause
