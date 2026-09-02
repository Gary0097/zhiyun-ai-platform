@echo off
setlocal
cd /d "%~dp0"
node apps\zhizaoyunAIOS\scripts\doctor.mjs %*
if errorlevel 1 pause
