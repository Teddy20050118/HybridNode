"""
HybridNode 简化启动脚本 - 仅测试 GUI
不加载分析引擎，用于测试 PyQt6 是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("🚀 Starting HybridNode GUI (minimal mode)...")

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QWidget
    from PyQt6.QtCore import Qt
    
    class SimpleWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("HybridNode - GUI Test")
            self.setGeometry(100, 100, 800, 600)
            
            # 创建中央 widget
            central = QWidget()
            layout = QVBoxLayout()
            
            # 添加文本显示
            text = QTextEdit()
            text.setReadOnly(True)
            text.setHtml("""
                <h1>✅ HybridNode GUI 测试成功!</h1>
                <p>PyQt6 已正确安装并运行。</p>
                <h3>下一步:</h3>
                <ul>
                    <li>修复 torch/torchvision 版本冲突</li>
                    <li>运行完整的 start_desktop.py</li>
                </ul>
                <h3>修复命令:</h3>
                <code style="background: #f0f0f0; padding: 10px; display: block;">
pip uninstall torch torchvision torchaudio transformers sentence-transformers -y<br>
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121<br>
pip install transformers sentence-transformers
                </code>
            """)
            layout.addWidget(text)
            
            # 添加关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)
            
            central.setLayout(layout)
            self.setCentralWidget(central)
    
    app = QApplication(sys.argv)
    window = SimpleWindow()
    window.show()
    
    print("✅ GUI 启动成功！")
    sys.exit(app.exec())
    
except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
