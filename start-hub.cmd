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

rem Local 运行环境隔离预检：Windows 需管理员权限（AppContainer ACL/回环），
rem 普通权限仅警告——Hub 本体能启动，但为用户拉起 Local 运行环境会失败
net session >nul 2>&1 || echo [WARN] Not elevated: Local runtimes require an administrator shell. Restart start-hub.cmd as admin for multi-user use.
set PYTHONIOENCODING=utf-8
rem Hub 数据（数据库/密钥，见 hub.yaml）固定落在安装目录下，避免随用户主目录漂移
set "QWENPAW_WORKING_DIR=%~dp0apps\zhizaoyunAIOS\workspace"
rem 每次启动都做版本/完整性校验：setup-hub.ps1 内置 Test-HubRuntime，
rem 就绪时立即退出；升级后旧 venv（如 2.1.0）会被自动重建为锁版本。
rem 默认在线安装；仅当离线包标记存在时才强制离线（UV_OFFLINE），
rem 避免源码安装因主 setup 未缓存 Hub 依赖 wheel 而首次启动失败。
set "HUB_SETUP_OPTS="
if exist "%~dp0apps\zhizaoyunAIOS\runtime\cache\OFFLINE-PACKAGE" set "HUB_SETUP_OPTS=-Offline"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-hub.ps1" %HUB_SETUP_OPTS% -CacheDir "%~dp0apps\zhizaoyunAIOS\runtime\cache"
if errorlevel 1 ( echo [ERROR] Hub runtime setup failed. See output above. & pause & exit /b 1 )
rem 生成派生配置：public_base_url 用本机局域网 IPv4（OAuth/MCP 回调地址
rem 必须与浏览器可见地址一致，官方 Hub 指南要求），hub.yaml 保持为模板
for /f "tokens=14" %%i in ('ipconfig ^| findstr /i "IPv4.192.168"') do set "LAN_IP=%%i"
if not defined LAN_IP set "LAN_IP=127.0.0.1"
powershell -NoProfile -Command "(Get-Content -Raw '%~dp0hub.yaml') -replace 'public_base_url: http://127.0.0.1:8000', ('public_base_url: http://' + $env:LAN_IP + ':8000') | Set-Content -Encoding utf8 '%~dp0hub.runtime.yaml'"
"%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" hub --host 0.0.0.0 --port 8000 --force-public --config "%~dp0hub.runtime.yaml"
pause
