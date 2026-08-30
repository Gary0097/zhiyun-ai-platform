@echo off
chcp 65001 >nul
title 智造云 AI-OS Hub（局域网多用户）
echo ==============================================
echo   智造云 AI-OS Hub — 局域网多用户模式
echo   首次使用：本机打开 http://127.0.0.1:8000 注册
echo   第一个注册的账号自动成为管理员
echo   之后同事用 http://<本机IP>:8000 访问
echo ==============================================
echo.
echo 本机 IPv4 地址：
ipconfig | findstr /i "IPv4"
echo.

set PYTHONIOENCODING=utf-8
"%~dp0apps\qwenpaw-embedded\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" hub --host 0.0.0.0 --port 8000 --force-public --config "%~dp0hub.yaml"
pause
