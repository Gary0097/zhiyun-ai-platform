@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-hub.ps1"
if errorlevel 1 ( echo [ERROR] Hub startup failed. & pause & exit /b 1 )
