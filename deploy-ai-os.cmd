@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   智造云 AI-OS 一键拉取 + 部署
echo ============================================

echo [1/3] 拉取最新代码 (mine = Gary0097/zhiyun-ai-platform)...
git switch master
if errorlevel 1 goto :error
git pull mine master
if errorlevel 1 goto :error

echo [2/3] 应用环境适配 (Desktop exe 用 Node cleanup)...
node apps\qwenpaw-embedded\scripts\apply-env-adapt.mjs
if errorlevel 1 goto :error

echo [3/3] 启动 AI-OS (http://127.0.0.1:8088)...
echo.
node apps\qwenpaw-embedded\scripts\start.mjs
goto :eof

:error
echo.
echo 部署失败，请查看上方错误信息。
pause
exit /b 1
