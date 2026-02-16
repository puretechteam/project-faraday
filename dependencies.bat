@echo off
REM Project Faraday - Dependency Checker
REM This script is informational only and performs no installations.

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Project Faraday - Dependency Checker
echo ========================================
echo.
echo This script checks for required dependencies.
echo It does NOT install or update anything.
echo.

REM Check Python
echo [Checking Python Installation...]
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python not found in PATH
    echo     Please install Python 3.7 or later
    echo.
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
    echo [OK] Python found: !PYTHON_VERSION!
    echo.
)

REM Check pip
echo [Checking pip...]
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] pip not found
    echo.
) else (
    for /f "tokens=2" %%i in ('python -m pip --version 2^>^&1') do set PIP_VERSION=%%i
    echo [OK] pip found: !PIP_VERSION!
    echo.
)

REM Check required packages
echo [Checking Required Packages...]
echo.

set PACKAGES=argon2-cffi cryptography cbor2 pystray Pillow

for %%p in (%PACKAGES%) do (
    python -c "import %%p" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [X] %%p - NOT INSTALLED
    ) else (
        for /f "tokens=2" %%v in ('python -c "import %%p; print(%%p.__version__)" 2^>^&1') do set PKG_VERSION=%%v
        echo [OK] %%p - !PKG_VERSION!
    )
)

echo.
echo ========================================
echo   Summary
echo ========================================
echo.
echo If any packages show [X], install them with:
echo   pip install -r requirements.txt
echo.
pause

