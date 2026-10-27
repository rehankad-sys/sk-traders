@echo off
chcp 65001 >nul
title SK Traders - Mobile App Preview
color 0B

echo ======================================================================
echo           SK TRADERS - ANDROID MOBILE APP (PREVIEW LAUNCHER)
echo ======================================================================
echo.
echo Launching Mobile App Touch UI...
echo.

cd /d "%~dp0"
python main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Could not start app. Make sure Python and Flet are installed.
    echo Run: pip install -r requirements.txt
    pause
)
