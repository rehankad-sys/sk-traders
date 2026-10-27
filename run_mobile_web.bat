@echo off
chcp 65001 >nul
title SK Traders - Mobile Web View
color 0E

echo ======================================================================
echo           SK TRADERS - MOBILE TOUCH WEB SERVER
echo ======================================================================
echo.
echo Starting local web server for Mobile Phone / PC Browser...
echo Open: http://localhost:8080/index.html
echo.

cd /d "%~dp0www"
start http://localhost:8080/index.html
python -m http.server 8080
