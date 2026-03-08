"""
HybridNode Desktop Application - 主程式入口
使用 PyQt6 + QtWebEngine 建立獨立桌面應用

取代原本的 FastAPI Web Server，提供原生桌面體驗
"""

import sys
import logging
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QUrl, QFile, QIODevice
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, 
    QWebEngineSettings, 
    QWebEngineScript
)
from PyQt6.QtWebChannel import QWebChannel

from src.bridge import HybridBridge

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HybridWebEnginePage(QWebEnginePage):
    """
    自定義 WebEnginePage 類別
    捕獲並轉印前端 JavaScript 控制台訊息到 Python Terminal
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("HybridWebEnginePage initialized with console logging")
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """
        覆寫控制台訊息處理函數
        將前端 JS 日誌映射到 Python 日誌系統
        
        Args:
            level: 日誌級別 (InfoMessageLevel, WarningMessageLevel, ErrorMessageLevel)
            message: 訊息內容
            lineNumber: 行號
            sourceID: 來源文件
        """
        # 格式化來源信息
        source = f"{sourceID}:{lineNumber}" if sourceID else f"line {lineNumber}"
        
        # 根據級別映射到 Python 日誌
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
            logger.info(f"[JS Console] {message} ({source})")
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            logger.warning(f"[JS Console] {message} ({source})")
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logger.error(f"[JS Console] {message} ({source})")
        else:
            logger.debug(f"[JS Console] {message} ({source})")


class HybridNodeWindow(QMainWindow):
    """
    HybridNode 主視窗
    
    功能：
    - 內嵌 QtWebEngine 渲染 React 前端
    - 透過 QWebChannel 連接 Python 後端
    - 提供原生資料夾選擇對話框
    - 顯示分析進度與結果
    - 捕獲並顯示前端 JS 錯誤
    """
    
    def __init__(self):
        super().__init__()
        
        # 視窗基本設置
        self.setWindowTitle("HybridNode - AI-Driven Code Dependency Analyzer")
        self.setGeometry(100, 100, 1280, 800)
        
        # 創建自定義 WebEnginePage（支持控制台映射）
        self.page = HybridWebEnginePage(self)
        
        # 配置 WebEngine 安全設置
        self._configure_web_settings()
        
        # 創建 WebEngine 視圖
        self.webview = QWebEngineView(self)
        self.webview.setPage(self.page)
        self.setCentralWidget(self.webview)
        
        # 創建 Bridge 橋接器
        self.bridge = HybridBridge(parent=self)
        
        # 設置 QWebChannel（連接 Python 與 JS）
        self.channel = QWebChannel()
        self.channel.registerObject('bridge', self.bridge)
        self.page.setWebChannel(self.channel)
        
        # 注入 qwebchannel.js（確保在頁面載入前可用）
        self._inject_qwebchannel_script()
        
        # 連接橋接器信號到 UI 更新
        self._connect_signals()
        
        # 載入前端頁面
        self._load_frontend()
        
        logger.info("HybridNode window initialized")
    
    def _configure_web_settings(self):
        """配置 WebEngine 安全與功能設置"""
        settings = self.page.settings()
        
        # 啟用本地內容訪問（file:// 協議）
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, 
            True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, 
            True
        )
        
        # 允許運行不安全內容（開發時需要）
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, 
            True
        )
        
        # 啟用 JavaScript（必須）
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, 
            True
        )
        
        # 啟用本地存儲（React 應用可能需要）
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, 
            True
        )
        
        # 啟用自動載入圖片
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AutoLoadImages, 
            True
        )
        
        # 啟用插件（如需要）
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PluginsEnabled, 
            True
        )
        
        logger.info("[SUCCESS] WebEngine settings configured for local file access")
    
    def _inject_qwebchannel_script(self):
        """
        注入 qwebchannel.js 腳本到頁面
        使用 PyQt6 內建的 Qt 資源系統（100% 可靠）
        """
        logger.info("[SEARCH] Loading qwebchannel.js from PyQt6 resources...")
        
        # 方法 1: 嘗試從 PyQt6 Qt 資源系統讀取
        resource_path = ":/qtwebchannel/qwebchannel.js"
        qfile = QFile(resource_path)
        
        if qfile.exists() and qfile.open(QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text):
            try:
                # 讀取 Qt 資源中的 qwebchannel.js
                qwebchannel_code = bytes(qfile.readAll()).decode('utf-8')
                logger.info(f"[SUCCESS] Loaded qwebchannel.js from Qt resources ({len(qwebchannel_code)} bytes)")
                qfile.close()
                
                # 創建注入腦本
                script = QWebEngineScript()
                script.setName("qwebchannel_builtin")
                script.setSourceCode(qwebchannel_code)
                script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
                script.setRunsOnSubFrames(False)
                script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
                
                # 插入到頁面腦本集合
                self.page.scripts().insert(script)
                logger.info("[SUCCESS] QWebChannel script injected successfully (PyQt6 builtin)")
                return
                
            except Exception as e:
                logger.error(f"[ERROR] Failed to load from Qt resources: {e}")
                qfile.close()
        
        # 方法 2: 回退到本地文件（frontend/build/qwebchannel.js）
        logger.info("[RETRY] Trying local qwebchannel.js file...")
        
        local_paths = [
            Path(__file__).parent.parent / "frontend" / "build" / "qwebchannel.js",
            Path(__file__).parent.parent / "frontend" / "public" / "qwebchannel.js",
        ]
        
        for local_path in local_paths:
            if local_path.exists():
                try:
                    with open(local_path, 'r', encoding='utf-8') as f:
                        qwebchannel_code = f.read()
                    
                    logger.info(f"[SUCCESS] Loaded qwebchannel.js from {local_path} ({len(qwebchannel_code)} bytes)")
                    
                    # 創建注入腦本
                    script = QWebEngineScript()
                    script.setName("qwebchannel_local")
                    script.setSourceCode(qwebchannel_code)
                    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
                    script.setRunsOnSubFrames(False)
                    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
                    
                    # 插入到頁面腦本集合
                    self.page.scripts().insert(script)
                    logger.info("[SUCCESS] QWebChannel script injected successfully (local file)")
                    return
                    
                except Exception as e:
                    logger.error(f"[ERROR] Failed to load from {local_path}: {e}")
        
        # 方法 3: 最後手段 - 使用精簡版本（僅當其他方法失敗）
        logger.warning("[WARN] Using fallback minimal QWebChannel loader")
        
        minimal_loader = """
        console.log('[WARN] QWebChannel not pre-loaded, waiting for HTML <script> tag...');
        """
        
        script = QWebEngineScript()
        script.setName("qwebchannel_fallback")
        script.setSourceCode(minimal_loader)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setRunsOnSubFrames(False)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        
        self.page.scripts().insert(script)
        logger.warning("[WARN] Relying on index.html to load qwebchannel.js")
    
    def _connect_signals(self):
        """連接 Python Bridge 信號到 UI 更新（可選）"""
        # 這裡可以連接一些信號來更新視窗標題或狀態欄
        # 例如：self.bridge.analysisProgress.connect(self._update_title)
        pass
    
    def _load_frontend(self):
        """載入前端 HTML 頁面"""
        # 嘗試載入編譯後的前端
        build_paths = [
            Path(__file__).parent.parent / "frontend" / "build" / "index.html",
            Path(__file__).parent.parent / "frontend" / "dist" / "index.html",
        ]
        
        for build_path in build_paths:
            if build_path.exists():
                # 使用絕對路徑並轉換為 file:// URL
                abs_path = build_path.resolve()
                url = QUrl.fromLocalFile(str(abs_path))
                
                logger.info(f"Loading frontend from: {url.toString()}")
                logger.info(f"  Absolute path: {abs_path}")
                
                self.webview.setUrl(url)
                
                # 連接 loadFinished 信號用於調試
                self.page.loadFinished.connect(self._on_load_finished)
                
                return
        
        # 如果找不到編譯後的前端，顯示錯誤頁面
        logger.error("[ERROR] Frontend build not found!")
        error_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>HybridNode - Build Not Found</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    text-align: center;
                    padding: 40px;
                    background: rgba(0,0,0,0.3);
                    border-radius: 10px;
                    backdrop-filter: blur(10px);
                }
                h1 { margin: 0 0 20px; }
                code {
                    background: rgba(255,255,255,0.2);
                    padding: 2px 6px;
                    border-radius: 3px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>[ERROR] Frontend Not Built</h1>
                <p>Please build the frontend first:</p>
                <pre>cd frontend
npm install
npm run build</pre>
                <p>Then restart the application.</p>
            </div>
        </body>
        </html>
        """
        self.page.setHtml(error_html)
    
    def _on_load_finished(self, success):
        """頁面載入完成時的回調（用於調試）"""
        if success:
            logger.info("[SUCCESS] Frontend page loaded successfully")
        else:
            logger.error("[ERROR] Frontend page failed to load")


def main():
    """主程式入口"""
    # 創建 Qt 應用
    app = QApplication(sys.argv)
    app.setApplicationName("HybridNode")
    app.setOrganizationName("HybridNode")
    
    # 創建主視窗
    window = HybridNodeWindow()
    window.show()
    
    logger.info("HybridNode desktop application started")
    
    # 進入事件循環
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
