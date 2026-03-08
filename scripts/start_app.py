"""
一鍵啟動腳本 - 自動啟動後端 API 和前端開發服務器

用法:
    python scripts/start_app.py
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# ANSI 顏色碼
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_header():
    """打印啟動信息"""
    print(f"""
{BLUE}╔═══════════════════════════════════════════════════════════╗
║              OmniTrace Application Launcher               ║
╚═══════════════════════════════════════════════════════════╝{RESET}
    """)


def check_dependencies():
    """檢查必要的依賴"""
    print(f"{BLUE}[1/4] Checking dependencies...{RESET}")
    
    # 檢查 Python 依賴
    try:
        import fastapi
        import uvicorn
        import torch
        import networkx
        print(f"{GREEN}✓ Python dependencies installed{RESET}")
    except ImportError as e:
        print(f"{YELLOW}⚠ Missing Python dependency: {e.name}{RESET}")
        print(f"   Run: pip install -r requirements.txt")
        return False
    
    # 檢查 frontend 目錄
    frontend_path = Path("frontend")
    if not frontend_path.exists():
        print(f"{YELLOW}⚠ Frontend directory not found{RESET}")
        return False
    
    # 檢查 node_modules
    node_modules = frontend_path / "node_modules"
    if not node_modules.exists():
        print(f"{YELLOW}⚠ Node modules not installed{RESET}")
        print(f"   Run: cd frontend && npm install")
        return False
    
    print(f"{GREEN}✓ Frontend dependencies installed{RESET}")
    return True


def check_graph_data():
    """檢查圖數據是否存在"""
    print(f"\n{BLUE}[2/4] Checking graph data...{RESET}")
    
    graph_file = Path("output/graph_data.pt")
    if not graph_file.exists():
        print(f"{YELLOW}⚠ Graph data not found: {graph_file}{RESET}")
        print(f"   Run: python main.py --dir ./examples --enable-stage3 --enable-labeling")
        
        response = input(f"\n   Do you want to generate it now? (y/n): ")
        if response.lower() == 'y':
            print(f"\n{BLUE}Generating graph data...{RESET}")
            result = subprocess.run([
                sys.executable, "main.py",
                "--dir", "./examples",
                "--enable-stage3",
                "--enable-labeling"
            ])
            
            if result.returncode != 0 or not graph_file.exists():
                print(f"{YELLOW}⚠ Failed to generate graph data{RESET}")
                return False
            
            print(f"{GREEN}✓ Graph data generated{RESET}")
        else:
            return False
    else:
        print(f"{GREEN}✓ Graph data found: {graph_file}{RESET}")
    
    return True


def start_backend():
    """啟動後端 API 服務器"""
    print(f"\n{BLUE}[3/4] Starting backend API server...{RESET}")
    
    # 獲取項目根目錄
    project_root = Path(__file__).parent.parent
    run_api_script = project_root / "run_api.py"
    
    # 使用 subprocess.Popen 在背景運行
    backend_process = subprocess.Popen(
        [sys.executable, str(run_api_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(project_root)  # 設置工作目錄為項目根目錄
    )
    
    # 等待啟動
    print(f"   Waiting for backend to start...")
    time.sleep(3)
    
    if backend_process.poll() is not None:
        print(f"{YELLOW}⚠ Backend failed to start{RESET}")
        return None
    
    print(f"{GREEN}✓ Backend API running at http://localhost:8000{RESET}")
    return backend_process


def start_frontend():
    """啟動前端開發服務器"""
    print(f"\n{BLUE}[4/4] Starting frontend dev server...{RESET}")
    
    # 檢查操作系統
    if sys.platform == "win32":
        npm_cmd = "npm.cmd"
    else:
        npm_cmd = "npm"
    
    # 啟動前端
    frontend_process = subprocess.Popen(
        [npm_cmd, "start"],
        cwd="frontend",
        shell=True if sys.platform == "win32" else False
    )
    
    print(f"   Waiting for frontend to start...")
    time.sleep(5)
    
    if frontend_process.poll() is not None:
        print(f"{YELLOW}⚠ Frontend failed to start{RESET}")
        return None
    
    print(f"{GREEN}✓ Frontend running at http://localhost:3000{RESET}")
    return frontend_process


def main():
    """主函數"""
    print_header()
    
    # 1. 檢查依賴
    if not check_dependencies():
        print(f"\n{YELLOW}Please install dependencies first.{RESET}\n")
        return 1
    
    # 2. 檢查圖數據
    if not check_graph_data():
        print(f"\n{YELLOW}Graph data is required to run the application.{RESET}\n")
        return 1
    
    # 3. 啟動後端
    backend = start_backend()
    if backend is None:
        print(f"\n{YELLOW}Failed to start backend.{RESET}\n")
        return 1
    
    # 4. 啟動前端
    frontend = start_frontend()
    if frontend is None:
        print(f"\n{YELLOW}Failed to start frontend.{RESET}\n")
        backend.terminate()
        return 1
    
    # 啟動成功
    print(f"""
{GREEN}╔═══════════════════════════════════════════════════════════╗
║          🎉 OmniTrace is now running!                     ║
╚═══════════════════════════════════════════════════════════╝{RESET}

{BLUE}Backend API:{RESET}     http://localhost:8000
{BLUE}API Docs:{RESET}        http://localhost:8000/docs
{BLUE}Frontend UI:{RESET}     http://localhost:3000

{YELLOW}Press Ctrl+C to stop all servers.{RESET}
    """)
    
    try:
        # 保持運行，等待用戶中斷
        backend.wait()
    except KeyboardInterrupt:
        print(f"\n\n{BLUE}Shutting down servers...{RESET}")
        backend.terminate()
        frontend.terminate()
        
        # 等待進程結束
        backend.wait(timeout=5)
        frontend.wait(timeout=5)
        
        print(f"{GREEN}✓ All servers stopped.{RESET}\n")
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n{YELLOW}Error: {e}{RESET}\n")
        sys.exit(1)
