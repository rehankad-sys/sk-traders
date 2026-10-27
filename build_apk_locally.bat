@echo off
chcp 65001 >nul
title SK Traders - Build Android APK
color 0A

echo ======================================================================
echo           SK TRADERS - LOCAL ANDROID APK BUILDER
echo ======================================================================
echo.
echo Checking for Android SDK and Flutter...
echo.

where flutter >nul 2>nul
if %errorlevel% neq 0 (
    echo [NOTE] Flutter / Android SDK is not detected in your local PATH.
    echo.
    echo To build the standalone .apk file with 1-click on cloud:
    echo 1. Push this project to GitHub.
    echo 2. Go to 'Actions' tab and run the workflow 'Build SK Traders Android APK'.
    echo 3. Download the generated 'SK_Traders_Accounting.apk' directly!
    echo.
    echo Alternatively, install Flutter SDK from https://flutter.dev and run this script again.
    echo.
    pause
    exit /b 0
)

echo Flutter detected! Starting Flet APK Build...
cd /d "%~dp0"
flet build apk --project "SK Traders Accounting" --org "com.sktraders.accounting"

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] APK Generated Successfully!
    echo Check the 'build\apk' folder.
) else (
    echo.
    echo [ERROR] Build encountered an error. Check logs above.
)

pause
