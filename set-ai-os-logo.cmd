@echo off
chcp 65001 >nul
rem Logo 维护入口（兼容 QUICKSTART 文档）：拖拽图片到本文件或带路径参数运行；--reset 恢复默认
setlocal
cd /d "%~dp0"
set "BRAND=apps\zhizaoyunAIOS\workspaceranding"
if "%~1"=="--reset" (
  del "%BRAND%\logo.json" >nul 2>&1
  echo [OK] Logo 已恢复默认（重启服务后生效）。& pause & exit /b 0
)
if "%~1"=="" ( echo 用法：把 logo 图片拖到本文件上，或运行 set-ai-os-logo.cmd ^<图片路径^> & pause & exit /b 1 )
if not exist "%~1" ( echo [错误] 找不到文件：%~1 & pause & exit /b 1 )
mkdir "%BRAND%" 2>nul
copy /y "%~1" "%BRAND%\custom-logo%~x1" >nul
set "MIME=image/png"
if /i "%~x1"==".jpg" set "MIME=image/jpeg"
if /i "%~x1"==".jpeg" set "MIME=image/jpeg"
if /i "%~x1"==".svg" set "MIME=image/svg+xml"
if /i "%~x1"==".webp" set "MIME=image/webp"
> "%BRAND%\logo.json" echo {"path": "%~dp0%BRAND%\custom-logo%~x1", "mime": "%MIME%"}
echo [OK] Logo 已设置（重启服务后生效，--reset 可恢复默认）。
pause
