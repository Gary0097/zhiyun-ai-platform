@echo off
rem 健康检查入口（保留跨平台维护入口，实际诊断由 doctor.mjs 承载）
chcp 65001 >nul
cd /d "%~dp0"
node apps\zhizaoyunAIOS\scripts\doctor.mjs
if errorlevel 1 pause
rem 办公版体检（aios-office 分支）：技能/依赖/规范/桥接/补丁修复
node apps\zhizaoyunAIOS\scripts\check-office-pack.mjs
pause
