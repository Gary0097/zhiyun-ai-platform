@echo off
setlocal
cd /d "%~dp0"
rem U盘离线包内置的便携 Node 优先于系统 Node（不存在时无影响）
if exist "extras\node\node.exe" set "PATH=%~dp0extras\node;%PATH%"
if not exist "apps\zhizaoyunAIOS\runtime\zhizaoyunAIOS\venv\Scripts\qwenpaw.exe" if not exist "apps\zhizaoyunAIOS\runtime\zhizaoyunAIOS\Scripts\qwenpaw.exe" (
  where qwenpaw >nul 2>nul
  if errorlevel 1 (
    echo Project QwenPaw runtime is missing. Run setup-ai-os.ps1 once.
    pause
    exit /b 1
  )
)
node apps\zhizaoyunAIOS\scripts\start.mjs
if errorlevel 1 pause
