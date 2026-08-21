@echo off
setlocal
cd /d "%~dp0"
node apps\qwenpaw-embedded\scripts\doctor.mjs %*
if errorlevel 1 pause
