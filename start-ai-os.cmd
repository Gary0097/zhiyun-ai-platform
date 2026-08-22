@echo off
setlocal
cd /d "%~dp0"
if not exist "apps\qwenpaw-embedded\runtime\qwenpaw\bin\qwenpaw.cmd" if not exist "apps\qwenpaw-embedded\runtime\qwenpaw\Scripts\qwenpaw.exe" (
  where qwenpaw >nul 2>nul
  if errorlevel 1 (
    echo Project QwenPaw runtime is missing. Run setup-ai-os.ps1 once.
    pause
    exit /b 1
  )
)
node apps\qwenpaw-embedded\scripts\start.mjs
if errorlevel 1 pause
