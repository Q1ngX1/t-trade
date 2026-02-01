#!/usr/bin/env python3
"""
T-Trade 一键启动脚本
跨平台支持 Windows/macOS/Linux

用法:
    python start.py web      # 启动 Web 仪表盘 (后端 + 前端)
    python start.py cli      # 启动 CLI 模式 (连接 TWS)
    python start.py demo     # 启动演示模式 (无需 TWS)
    python start.py --help   # 查看帮助
"""

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.absolute()
FRONTEND_DIR = ROOT_DIR / "frontend"


def check_uv():
    """检查 uv 是否安装"""
    if shutil.which("uv") is None:
        print("[ERROR] 未找到 uv，请先安装: https://docs.astral.sh/uv/")
        sys.exit(1)


def check_node():
    """检查 Node.js 是否安装"""
    if shutil.which("npm") is None:
        print("[ERROR] 未找到 npm，请先安装 Node.js: https://nodejs.org/")
        return False
    return True


def run_command(cmd, cwd=None, background=False):
    """运行命令"""
    print(f"[RUN] {' '.join(cmd)}")
    
    if background:
        if platform.system() == "Windows":
            # Windows 后台进程
            return subprocess.Popen(
                cmd,
                cwd=cwd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        else:
            # Unix 后台进程
            return subprocess.Popen(
                cmd,
                cwd=cwd,
                preexec_fn=os.setsid,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
    else:
        return subprocess.run(cmd, cwd=cwd)


def install_frontend_deps():
    """安装前端依赖"""
    if not (FRONTEND_DIR / "node_modules").exists():
        print("[INFO] 安装前端依赖...")
        run_command(["npm", "install"], cwd=FRONTEND_DIR)


def start_web(api_port=8000, frontend_port=5173):
    """启动 Web 模式 (后端 + 前端)"""
    check_uv()
    
    if not check_node():
        print("[WARN] 将只启动后端 API")
        run_command(["uv", "run", "uvicorn", "tbot.api.main:app", 
                     "--host", "0.0.0.0", "--port", str(api_port), "--reload"],
                    cwd=ROOT_DIR)
        return
    
    install_frontend_deps()
    
    processes = []
    
    try:
        # 启动后端
        print(f"\n[INFO] 启动后端 API (http://localhost:{api_port})")
        backend = run_command(
            ["uv", "run", "uvicorn", "tbot.api.main:app", 
             "--host", "0.0.0.0", "--port", str(api_port), "--reload"],
            cwd=ROOT_DIR,
            background=True
        )
        processes.append(backend)
        
        # 等待后端启动
        time.sleep(2)
        
        # 启动前端
        print(f"\n[INFO] 启动前端 (http://localhost:{frontend_port})")
        frontend = run_command(
            ["npm", "run", "dev", "--", "--port", str(frontend_port)],
            cwd=FRONTEND_DIR,
            background=True
        )
        processes.append(frontend)
        
        print(f"\n{'='*50}")
        print(f"  T-Trade Web 仪表盘已启动")
        print(f"  前端: http://localhost:{frontend_port}")
        print(f"  后端: http://localhost:{api_port}")
        print(f"  按 Ctrl+C 停止所有服务")
        print(f"{'='*50}\n")
        
        # 实时输出日志
        while True:
            for p in processes:
                if p.poll() is not None:
                    # 进程已结束
                    output = p.stdout.read().decode() if p.stdout else ""
                    if output:
                        print(output)
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[INFO] 正在停止服务...")
    finally:
        for p in processes:
            try:
                if platform.system() == "Windows":
                    p.terminate()
                else:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        print("[INFO] 服务已停止")


def start_cli(port=7497):
    """启动 CLI 模式"""
    check_uv()
    print(f"\n[INFO] 启动 CLI 模式，连接 TWS 端口 {port}")
    run_command(["uv", "run", "tbot", "run", "--port", str(port)], cwd=ROOT_DIR)


def start_demo():
    """启动演示模式"""
    check_uv()
    print("\n[INFO] 启动演示模式 (无需 TWS 连接)")
    run_command(["uv", "run", "tbot", "demo"], cwd=ROOT_DIR)


def main():
    parser = argparse.ArgumentParser(
        description="T-Trade 一键启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python start.py web              启动 Web 仪表盘
  python start.py web --port 8080  指定后端端口
  python start.py cli              连接 TWS (端口 7497)
  python start.py cli --tws 7496   连接 TWS 实盘
  python start.py demo             演示模式
        """
    )
    
    subparsers = parser.add_subparsers(dest="mode", help="运行模式")
    
    # web 子命令
    web_parser = subparsers.add_parser("web", help="启动 Web 仪表盘")
    web_parser.add_argument("--port", "-p", type=int, default=8000, 
                            help="后端 API 端口 (默认 8000)")
    web_parser.add_argument("--frontend-port", "-f", type=int, default=5173,
                            help="前端端口 (默认 5173)")
    
    # cli 子命令
    cli_parser = subparsers.add_parser("cli", help="启动 CLI 模式")
    cli_parser.add_argument("--tws", "-t", type=int, default=7497,
                            help="TWS 端口 (默认 7497 纸盘)")
    
    # demo 子命令
    subparsers.add_parser("demo", help="启动演示模式")
    
    args = parser.parse_args()
    
    if args.mode is None:
        parser.print_help()
        print("\n[TIP] 快速启动: python start.py web")
        sys.exit(0)
    
    os.chdir(ROOT_DIR)
    
    if args.mode == "web":
        start_web(api_port=args.port, frontend_port=args.frontend_port)
    elif args.mode == "cli":
        start_cli(port=args.tws)
    elif args.mode == "demo":
        start_demo()


if __name__ == "__main__":
    main()
