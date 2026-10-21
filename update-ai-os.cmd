@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-ai-os.ps1" %*
exit /b %errorlevel%
