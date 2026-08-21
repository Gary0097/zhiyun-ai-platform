@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo 请把 PNG、JPG、SVG 或 WebP Logo 文件拖到本脚本上。
  pause
  exit /b 1
)
python apps\qwenpaw-embedded\scripts\set-logo.py "%~1"
if errorlevel 1 pause
