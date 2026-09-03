@echo off
chcp 65001 >nul
title 灵泽万川智造云 Hub（局域网多用户）
echo ==============================================
echo   灵泽万川智造云 Hub — 局域网多用户模式
echo   首次使用：本机打开 http://127.0.0.1:8000 注册
echo   第一个注册的账号自动成为管理员
echo   之后同事用 http://<本机IP>:8000 访问
echo ==============================================
echo.
echo 本机 IPv4 地址：
ipconfig | findstr /i "IPv4"
echo.

set PYTHONIOENCODING=utf-8
rem Hub 运行环境缺失或版本不符时自动供给（模型账号请在 Hub 管理界面统一配置）
if not exist "%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" (
  echo [提示] 首次运行：正在安装 QwenPaw Hub 运行环境（数分钟）...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-hub.ps1" -Offline -CacheDir "apps\zhizaoyunAIOS\runtime\cache"
  if errorlevel 1 ( echo [错误] Hub 运行环境安装失败，请查看上方输出。 & pause & exit /b 1 )
)
"%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" hub --host 0.0.0.0 --port 8000 --force-public --config "%~dp0hub.yaml"
pause
