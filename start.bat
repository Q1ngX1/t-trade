@echo off
REM T-Trade 启动脚本 (Windows)
REM 用法: start.bat [web|cli|demo]

cd /d "%~dp0"

set MODE=%1
if "%MODE%"=="" set MODE=web

if "%MODE%"=="web" (
    echo 启动 Web 仪表盘...
    python start.py web
    goto :end
)

if "%MODE%"=="cli" (
    echo 启动 CLI 模式...
    python start.py cli
    goto :end
)

if "%MODE%"=="demo" (
    echo 启动演示模式...
    python start.py demo
    goto :end
)

echo 用法: %0 [web^|cli^|demo]
echo   web  - 启动 Web 仪表盘 (默认)
echo   cli  - 启动 CLI 模式 (需要 TWS)
echo   demo - 启动演示模式

:end
