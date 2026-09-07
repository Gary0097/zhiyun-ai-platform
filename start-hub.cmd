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

rem Local runtime isolation preflight: Windows requires an administrator
rem shell (AppContainer ACLs). Warn only when not elevated.
net session >nul 2>&1 || echo [WARN] Not elevated: Local runtimes require an administrator shell. Restart start-hub.cmd as admin for multi-user use.
set PYTHONIOENCODING=utf-8
rem Pin Hub data (db/secrets, see hub.yaml) under the install dir
set "QWENPAW_WORKING_DIR=%~dp0apps\zhizaoyunAIOS\workspace"
rem Revalidate the hub runtime on every launch (fast probe when ready).
rem Online install by default; force offline only when the package marker exists.
set "HUB_SETUP_OPTS="
if exist "%~dp0apps\zhizaoyunAIOS\runtime\cache\OFFLINE-PACKAGE" set "HUB_SETUP_OPTS=-Offline"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-hub.ps1" %HUB_SETUP_OPTS% -CacheDir "%~dp0apps\zhizaoyunAIOS\runtime\cache"
if errorlevel 1 ( echo [ERROR] Hub runtime setup failed. See output above. & pause & exit /b 1 )
rem Derive hub.runtime.yaml: public_base_url set to this host LAN IPv4
rem (OAuth/MCP callbacks must match the browser-visible address).
powershell -NoProfile -Command "$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and ($_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' -or $_.IPAddress -match '^172\\.(1[6-9]|2[0-9]|3[01])\\.') } | Select-Object -First 1; $lan = if ($ip) { $ip.IPAddress } else { '127.0.0.1' }; (Get-Content -Raw '%~dp0hub.yaml') -replace 'public_base_url: http://127.0.0.1:8000', ('public_base_url: http://' + $lan + ':8000') | Set-Content -Encoding utf8 '%~dp0hub.runtime.yaml'"
"%~dp0apps\zhizaoyunAIOS\runtime\qwenpaw-hub\venv\Scripts\qwenpaw.exe" hub --host 0.0.0.0 --port 8000 --force-public --config "%~dp0hub.runtime.yaml"
pause
