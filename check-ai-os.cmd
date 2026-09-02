@echo off
setlocal
cd /d "%~dp0"
node apps\zhizaoyunAIOS\scripts\health-report.mjs
if errorlevel 1 pause
