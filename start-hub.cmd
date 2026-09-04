@echo off
chcp 65001 >nul
title Lingze Wanchuan Zhizaoyun AI-OS Hub
echo ==============================================
echo   Lingze Wanchuan Zhizaoyun AI-OS Hub (LAN multi-user)
echo   First run: open http://127.0.0.1:8000 and register
echo   The first registered account becomes the admin
echo   Then coworkers visit http://THIS-PC-IP:8000
echo ==============================================
echo.
echo Local IPv4 addresses:
ipconfig | findstr /i "IPv4"
echo.

set PYTHONIOENCODING=utf-8
rem Hub 运行环境缺失或版本不符时自动供给（模型账号请在 Hub 管理界面统一配置）
if not exist "%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" (
  echo [INFO] First run: installing QwenPaw Hub runtime - takes a few minutes...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-hub.ps1" -Offline -CacheDir "apps\zhizaoyunAIOS\runtime\cache"
  if errorlevel 1 ( echo [ERROR] Hub runtime setup failed. See output above. & pause & exit /b 1 )
)
"%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" hub --host 0.0.0.0 --port 8000 --force-public --config "%~dp0hub.yaml"
pause
