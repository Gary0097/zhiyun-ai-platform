@echo off
setlocal
cd /d "%~dp0"
node apps\qwenpaw-embedded\scripts\health-report.mjs
if errorlevel 1 pause
