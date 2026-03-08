"""
HybridNode Desktop Application 啟動腳本
一鍵啟動 PyQt6 桌面應用

用法:
    python start_desktop.py
"""

import sys
import os
import io
from pathlib import Path

# 设置控制台输出为 UTF-8（Windows 兼容）
if sys.platform == 'win32':
    try:
        # 尝试设置 UTF-8 输出
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass  # 如果失败，使用默认编码

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# ANSI 顏色碼
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def print_header():
    """打印啟動信息"""
    print(f"""
{BLUE}╔═══════════════════════════════════════════════════════════╗
║          HybridNode Desktop Application Launcher          ║
║              AI-Driven Code Dependency Analyzer           ║
╚═══════════════════════════════════════════════════════════╝{RESET}
    """)


def check_dependencies():
    """檢查必要的依賴"""
    print(f"{BLUE}[1/3] Checking Python dependencies...{RESET}")
    
    missing_deps = []
    
    # 檢查核心依賴
    required_packages = {
        'PyQt6': 'PyQt6',
        'PyQt6.QtWebEngineWidgets': 'PyQt6-WebEngine',
        'torch': 'torch',
        'networkx': 'networkx',
        'src.stage1_parser': 'project modules (run from project root)',
    }
    
    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
            print(f"  [OK] {package_name}")
        except ImportError:
            print(f"  [X] {package_name} {YELLOW}(missing){RESET}")
            missing_deps.append(package_name)
    
    if missing_deps:
        print(f"\n{YELLOW}Missing dependencies:{RESET}")
        for dep in missing_deps:
            print(f"  - {dep}")
        print(f"\n{BLUE}Install them with:{RESET}")
        print(f"  pip install {' '.join(missing_deps)}")
        print(f"\n{YELLOW}Note: If you're using conda/venv, make sure it's activated.{RESET}")
        
        # 不阻止启动，让用户决定
        response = input(f"\n{YELLOW}Continue anyway? (y/n): {RESET}")
        if response.lower() != 'y':
            return False
    
    print(f"\n{GREEN}[OK] Dependencies check completed{RESET}")
    return True


def check_frontend():
    """檢查前端編譯產物"""
    print(f"\n{BLUE}[2/3] Checking frontend build...{RESET}")
    
    build_paths = [
        Path("frontend/build/index.html"),
        Path("frontend/dist/index.html"),
    ]
    
    for build_path in build_paths:
        if build_path.exists():
            print(f"  [OK] Found frontend build at: {build_path}")
            return True
    
    print(f"  [WARN] No frontend build found")
    print(f"\n{BLUE}To build the frontend:{RESET}")
    print(f"  cd frontend")
    print(f"  npm install")
    print(f"  npm run build")
    print(f"\n{YELLOW}Note:{RESET} The app will attempt to connect to dev server (localhost:3000)")
    print(f"      or show instructions to build the frontend.")
    
    return True  # 不阻止啟動，允許使用開發服務器


def check_qwebchannel():
    """檢查 qwebchannel.js 文件"""
    print(f"\n{BLUE}Checking qwebchannel.js...{RESET}")
    
    qwebchannel_paths = [
        Path("frontend/public/qwebchannel.js"),
        Path("frontend/build/qwebchannel.js"),
        Path("frontend/dist/qwebchannel.js"),
    ]
    
    found = False
    for path in qwebchannel_paths:
        if path.exists():
            print(f"  [OK] Found at: {path}")
            found = True
            break
    
    if not found:
        print(f"  [WARN] qwebchannel.js not found locally")
        print(f"      Make sure to include it in your index.html from CDN:")
        print(f'      <script src="https://cdn.jsdelivr.net/npm/@qtproject/qtwebchannel@5.15.2/qwebchannel.js"></script>')


def start_application():
    """啟動桌面應用"""
    print(f"\n{BLUE}[3/3] Starting HybridNode Desktop...{RESET}\n")
    
    try:
        # 導入並啟動 GUI
        from src.gui_main import main
        
        print(f"{GREEN}>> Launching application...{RESET}\n")
        
        # 執行主程式
        main()
        
    except Exception as e:
        print(f"\n{RED}[ERROR] Failed to start application:{RESET}")
        print(f"   {str(e)}")
        
        import traceback
        print(f"\n{YELLOW}Traceback:{RESET}")
        print(traceback.format_exc())
        
        return False
    
    return True


def main():
    """主函數"""
    print_header()
    
    # 檢查依賴
    if not check_dependencies():
        print(f"\n{RED}[ERROR] Please install missing dependencies before running.{RESET}")
        return 1
    
    # 檢查前端
    check_frontend()
    
    # 檢查 qwebchannel.js
    check_qwebchannel()
    
    # 啟動應用
    print("\n" + "=" * 60)
    
    if not start_application():
        print(f"\n{RED}[ERROR] Application failed to start.{RESET}")
        return 1
    
    print(f"\n{GREEN}✅ Application closed successfully.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
