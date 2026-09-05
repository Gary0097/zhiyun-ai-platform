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
rem 每次启动都做版本/完整性校验：setup-hub.ps1 内置 Test-HubRuntime，
rem 就绪时立即退出；升级后旧 venv（如 2.1.0）会被自动重建为锁版本。
rem 默认在线安装；仅当离线包标记存在时才强制离线（UV_OFFLINE），
rem 避免源码安装因主 setup 未缓存 Hub 依赖 wheel 而首次启动失败。
set "HUB_SETUP_OPTS="
if exist "%~dp0apps\zhizaoyunAIOS\runtime\cache\OFFLINE-PACKAGE" set "HUB_SETUP_OPTS=-Offline"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-hub.ps1" %HUB_SETUP_OPTS% -CacheDir "%~dp0apps\zhizaoyunAIOS\runtime\cache"
if errorlevel 1 ( echo [ERROR] Hub runtime setup failed. See output above. & pause & exit /b 1 )
"%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" hub --host 0.0.0.0 --port 8000 --force-public --config "%~dp0hub.yaml"
pause
