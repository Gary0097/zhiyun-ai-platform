@echo off
chcp 65001 >nul
title 灵泽万川智造云 一键安装
echo ============================================
echo   灵泽万川智造云 一键安装（在线模式）
echo   安装完成后自动启动并打开浏览器
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Node.js（需要 20 或以上）。
  echo 请先安装：https://nodejs.org/zh-cn
  pause
  exit /b 1
)
for /f "tokens=1 delims=." %%v in ('node -p "process.versions.node.split('.')[0]"') do set NODE_MAJOR=%%v
if %NODE_MAJOR% LSS 20 (
  echo [错误] Node.js 版本过低（需要 20 或以上，当前版本号主版本 %NODE_MAJOR%）。
  pause
  exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Git。
  echo 请先安装：https://git-scm.com/download/win
  pause
  exit /b 1
)

echo [1/3] 安装运行时与锁定应用（首次约 3-10 分钟，取决于网络）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-ai-os.ps1"
if errorlevel 1 (
  echo [错误] 安装失败，请查看上方日志。
  pause
  exit /b 1
)

echo.
echo [2/3] 启动服务...
start "" "%~dp0start-ai-os.cmd"

echo [3/3] 等待服务就绪后打开浏览器...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 40;$i++){ try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8088/api/version' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){$ok=$true; break} } catch { Start-Sleep 3 } }; if($ok){ Start-Process 'http://127.0.0.1:8088' } else { Write-Host '服务未在预期时间内就绪，请稍后手动打开 http://127.0.0.1:8088' }"

echo.
echo 安装完成！默认管理员账号见 README（首次登录后请立即修改密码）。
echo 如需停止服务，运行 diagnose-ai-os.cmd 查看说明。
pause
