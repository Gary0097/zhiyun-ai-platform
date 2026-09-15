@echo off
rem 健康检查入口（保留跨平台维护入口，实际诊断由 doctor.mjs 承载）
chcp 65001 >nul
cd /d "%~dp0"
node apps\zhizaoyunAIOS\scripts\doctor.mjs
pause
