#!/bin/bash
# T-Trade 启动脚本 (macOS/Linux)
# 用法: ./start.sh [web|cli|demo]

cd "$(dirname "$0")"

MODE=${1:-web}

case $MODE in
    web)
        echo "启动 Web 仪表盘..."
        python3 start.py web
        ;;
    cli)
        echo "启动 CLI 模式..."
        python3 start.py cli
        ;;
    demo)
        echo "启动演示模式..."
        python3 start.py demo
        ;;
    *)
        echo "用法: $0 [web|cli|demo]"
        echo "  web  - 启动 Web 仪表盘 (默认)"
        echo "  cli  - 启动 CLI 模式 (需要 TWS)"
        echo "  demo - 启动演示模式"
        exit 1
        ;;
esac
