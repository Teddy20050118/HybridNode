"""
自動導出 PyQt6 內建的 qwebchannel.js 到前端目錄
確保前端可以使用本地版本，避免 CDN 依賴

使用方法：
    python scripts/export_qwebchannel.py
"""

import sys
from pathlib import Path
from PyQt6.QtCore import QFile, QIODevice

# 項目根目錄
PROJECT_ROOT = Path(__file__).parent.parent

# 目標路徑
FRONTEND_PUBLIC = PROJECT_ROOT / "frontend" / "public"
OUTPUT_FILE = FRONTEND_PUBLIC / "qwebchannel.js"


def export_qwebchannel():
    """從 PyQt6 Qt 資源系統導出 qwebchannel.js"""
    
    print("🔍 Searching for qwebchannel.js in PyQt6 resources...")
    
    # PyQt6 內建的 qwebchannel.js 資源路徑
    resource_path = ":/qtwebchannel/qwebchannel.js"
    
    # 嘗試讀取 Qt 資源
    qfile = QFile(resource_path)
    
    if not qfile.exists():
        print(f"❌ Error: Resource not found at {resource_path}")
        print("\n📝 Alternative: Downloading from Qt repository...")
        
        # 備用方案：從可用的 CDN 下載
        try:
            import urllib.request
            
            # 嘗試多個 CDN 源
            cdn_urls = [
                "https://raw.githubusercontent.com/qt/qtwebchannel/5.15/examples/webchannel/shared/qwebchannel.js",
                "https://cdn.jsdelivr.net/gh/qt/qtwebchannel@5.15/examples/webchannel/shared/qwebchannel.js",
                "https://raw.githubusercontent.com/qt/qtwebchannel/dev/examples/webchannel/shared/qwebchannel.js",
            ]
            
            content = None
            successful_url = None
            
            for cdn_url in cdn_urls:
                try:
                    print(f"📡 Trying: {cdn_url}")
                    with urllib.request.urlopen(cdn_url, timeout=10) as response:
                        content = response.read().decode('utf-8')
                        successful_url = cdn_url
                        break
                except Exception as e:
                    print(f"   ❌ Failed: {e}")
                    continue
            
            if not content:
                print("❌ All CDN sources failed")
                return False
            if not content:
                print("❌ All CDN sources failed")
                return False
            
            # 確保目錄存在
            FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)
            
            # 寫入文件
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Downloaded from: {successful_url}")
            print(f"✅ Saved to: {OUTPUT_FILE}")
            print(f"📦 File size: {len(content)} bytes")
            
            print("\n✅ Export completed successfully!")
            print("\n📋 Next steps:")
            print("   1. Run: cd frontend && npm run build")
            print("   2. The file will be copied to frontend/build/qwebchannel.js")
            print("   3. Run: python start_desktop.py")
            return True
            
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
    
    # 打開資源文件（只讀模式）
    if not qfile.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
        print(f"❌ Error: Cannot open resource file: {qfile.errorString()}")
        return False
    
    try:
        # 讀取內容
        content = bytes(qfile.readAll()).decode('utf-8')
        print(f"✅ Resource loaded successfully ({len(content)} bytes)")
        
        # 確保目錄存在
        FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)
        
        # 寫入到前端 public 目錄
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Exported to: {OUTPUT_FILE}")
        print(f"📂 Directory: {FRONTEND_PUBLIC}")
        
        # 驗證文件
        if OUTPUT_FILE.exists():
            size = OUTPUT_FILE.stat().st_size
            print(f"📦 File size: {size} bytes")
            print("\n✅ Export completed successfully!")
            print("\n📋 Next steps:")
            print("   1. Run: cd frontend && npm run build")
            print("   2. The file will be copied to frontend/build/qwebchannel.js")
            print("   3. Run: python start_desktop.py")
            return True
        else:
            print("❌ Error: File export failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during export: {e}")
        return False
    finally:
        qfile.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  PyQt6 QWebChannel.js Local Export Tool")
    print("=" * 60)
    print()
    
    success = export_qwebchannel()
    
    if success:
        sys.exit(0)
    else:
        print("\n❌ Export failed. Please check the error messages above.")
        sys.exit(1)
