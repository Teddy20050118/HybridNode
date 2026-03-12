"""
HybridNode Bridge - Python-JavaScript 橋接層
使用 QWebChannel 實現前端 JS 與後端 Python 的通訊
取代原本的 FastAPI REST API
"""

import sys
import json
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any
import traceback

from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QThread
from PyQt6.QtWidgets import QFileDialog
import torch
import networkx as nx

# 導入分析模組
from src.stage1_parser import ClangParser, find_source_files
from src.stage2_graph import SoftwareGraph, analyze_codebase
from src.stage3_features import FeatureExtractor, to_pyg_data, preprocess_graph
from src.stage3_labeler import apply_labels, save_labels_report
from src.stage5_inference import BugPredictor
from src.api import GraphDataConverter, load_graph_data

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def sanitize_for_json(obj: Any) -> Any:
    """
    遞迴轉換物件為 JSON 安全的 Python 原生類型
    處理 NumPy, PyTorch Tensor, Clang 對象, 和其他非標準類型
    
    Args:
        obj: 要轉換的物件
        
    Returns:
        JSON 安全的 Python 原生類型
    """
    # 檢測 Clang 相關對象（TranslationUnit, Cursor 等）
    obj_type_name = type(obj).__name__
    if 'TranslationUnit' in obj_type_name or 'Cursor' in obj_type_name:
        logger.warning(f"[WARN] 偵測到不可序列化的 Clang 對象: {obj_type_name}")
        return f"<Unserializable: {obj_type_name}>"
    
    # NumPy 整數類型
    if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    
    # NumPy 浮點類型
    if isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    
    # NumPy 陣列
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    
    # PyTorch Tensor
    if isinstance(obj, torch.Tensor):
        return obj.cpu().detach().numpy().tolist()
    
    # 字典 - 遞迴處理
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    
    # 列表/元組 - 遞迴處理
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    
    # 基本類型直接返回
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    
    # 其他未知類型 - 防禦性處理
    try:
        # 嘗試檢查是否為可序列化的內建類型
        import json
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        # 無法序列化，記錄警告並返回描述字串
        logger.warning(f"[WARN] 無法序列化的物件類型: {type(obj).__name__}")
        return f"<Unserializable: {type(obj).__name__}>"


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    安全的 JSON 序列化函數
    先遞迴清理物件，再進行 JSON 序列化
    
    Args:
        obj: 要序列化的對象
        **kwargs: 傳遞給 json.dumps 的額外參數
        
    Returns:
        JSON 字符串
    """
    # 先清理物件
    sanitized = sanitize_for_json(obj)
    
    # 設定預設參數（如果未提供）
    if 'ensure_ascii' not in kwargs:
        kwargs['ensure_ascii'] = False
    
    # 再序列化
    return json.dumps(sanitized, **kwargs)


class AnalysisWorker(QThread):
    """
    分析工作執行緒 - 在背景執行耗時的分析任務
    避免阻塞 GUI 主執行緒
    """
    
    # 信號定義
    progress = pyqtSignal(str, int)  # (message, percentage)
    finished = pyqtSignal(dict)  # 分析完成，返回圖數據
    error = pyqtSignal(str)  # 錯誤信息
    
    def __init__(self, project_path: str):
        super().__init__()
        self.project_path = project_path
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
    
    def run(self):
        """執行完整的分析流程：Stage 1-3 + GNN 推論"""
        try:
            # Stage 1: 解析 C++ 原始碼
            self.progress.emit("[STAGE 1] 正在解析 C++ 原始碼檔案...", 10)
            source_files = find_source_files(self.project_path)
            
            if not source_files:
                self.error.emit(f"在 {self.project_path} 中找不到 C/C++ 原始碼檔案")
                return
            
            logger.info(f"[INFO] 找到 {len(source_files)} 個原始碼檔案")
            
            parser = ClangParser()
            all_data = []
            
            for i, file_path in enumerate(source_files):
                progress_pct = 10 + int((i / len(source_files)) * 20)
                self.progress.emit(f"[PARSE] 正在解析 {Path(file_path).name}...", progress_pct)
                
                try:
                    # ✅ 使用 parse_file_safe() 返回可序列化的字典資料
                    # ❌ 不要使用 parse_file()，它返回 TranslationUnit 對象
                    data = parser.parse_file_safe(file_path)
                    
                    # 清洗資料：確保不包含任何 Clang 對象
                    if 'translation_unit' in data:
                        del data['translation_unit']
                    if 'cursor' in data:
                        del data['cursor']
                    
                    all_data.append(data)
                except Exception as e:
                    logger.warning(f"[WARN] 解析失敗 {file_path}: {e}")
            
            # 保存解析結果
            parsed_output = self.output_dir / "parsed_data.json"
            with open(parsed_output, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[INFO] 階段 1 解析結果已儲存至 {parsed_output}")
            
            # Stage 2: 構建相依性圖
            self.progress.emit("[STAGE 2] 正在建構相依性圖...", 35)
            # ✅ 傳遞 JSON 檔案路徑而不是專案資料夾路徑
            software_graph = analyze_codebase(str(parsed_output), str(self.output_dir))
            # 獲取內部的 NetworkX 圖形對象
            nx_graph = software_graph.graph
            
            # Stage 3: 特徵提取與標註
            self.progress.emit("[STAGE 3] 正在提取特徵...", 50)

            # 步驟 1: 預處理 NetworkX 圖形
            logger.info("[INFO] 正在預處理 NetworkX 圖形...")
            nx_graph = preprocess_graph(nx_graph)

            # [INFO] 安全檢查：若圖形節點數為 0，表示所有檔案解析失敗，
            # 不應繼續進入特徵提取階段，否則會觸發空矩陣崩潰。
            if nx_graph.number_of_nodes() == 0:
                msg = (
                    f"[ERROR] 專案 '{self.project_path}' 中所有檔案的解析結果均為空，"
                    "無法建立有效節點。"
                    "請確認目錄中包含可解析的 .cpp / .h 檔案，且不依賴特殊編譯器擴充。"
                )
                logger.error(msg)
                self.error.emit(msg)
                return

            # 步驟 2: 轉換為 PyTorch Geometric 格式
            logger.info("[INFO] 轉換為 PyTorch Geometric 格式...")
            pyg_data = to_pyg_data(nx_graph)
            
            # Stage 3.5: Bug 標註
            self.progress.emit("[STAGE 3.5] 正在套用錯誤標籤...", 65)
            pyg_data, labels_report = apply_labels(pyg_data, nx_graph)
            
            # 保存標註報告
            save_labels_report(labels_report, str(self.output_dir / "labels_report.json"))
            
            # 儲存圖資料
            graph_output = self.output_dir / "graph_data.pt"
            torch.save(pyg_data, graph_output)
            logger.info(f"[INFO] 圖資料已儲存至 {graph_output}")
            
            # Stage 5: GNN 推論（如果模型存在）
            model_path = Path("models/omni_gat_best.pth")
            if model_path.exists():
                self.progress.emit("[STAGE 5] 正在執行 GNN 推論...", 80)
                try:
                    predictor = BugPredictor(str(model_path))
                    predictions = predictor.predict(pyg_data)
                    
                    # 將預測結果加入 PyG 數據
                    pred_tensor = torch.tensor([predictions.get(nid, 0.0) 
                                              for nid in pyg_data.node_ids])
                    pyg_data.pred_scores = pred_tensor
                    
                    # 重新儲存包含預測結果的資料
                    torch.save(pyg_data, graph_output)
                    logger.info("[INFO] GNN 預測結果已加入圖資料")
                    
                except Exception as e:
                    logger.warning(f"[WARN] GNN 推論失敗: {e}")
                    # 繼續執行，不中斷流程
            
            # 轉換為前端格式
            self.progress.emit("[CONVERT] 正在轉換為視覺化格式...", 90)
            
            # 重建 NetworkX 圖（包含更新的屬性）
            nx_graph = self._rebuild_networkx_graph(pyg_data)
            
            # 使用現有的轉換器
            converter = GraphDataConverter(nx_graph, pyg_data, labels_report)
            graph_data = converter.convert_to_react_force_graph()
            
            self.progress.emit("[COMPLETE] 分析已成功完成", 100)
            self.finished.emit(graph_data)
            
        except Exception as e:
            error_msg = f"分析失敗: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"[ERROR] {error_msg}")
            self.error.emit(error_msg)
    
    def _rebuild_networkx_graph(self, pyg_data) -> nx.DiGraph:
        """從 PyG 數據重建 NetworkX 圖"""
        graph = nx.DiGraph()
        
        # 添加節點
        node_ids = pyg_data.node_ids
        node_names = pyg_data.node_names if hasattr(pyg_data, 'node_names') else {}
        
        for node_id in node_ids:
            attrs = {'name': node_names.get(node_id, node_id)}
            if hasattr(pyg_data, 'node_attributes'):
                attrs.update(pyg_data.node_attributes.get(node_id, {}))
            graph.add_node(node_id, **attrs)
        
        # 添加邊
        edge_index = pyg_data.edge_index
        for i in range(edge_index.shape[1]):
            src_idx = int(edge_index[0, i].item())
            tgt_idx = int(edge_index[1, i].item())
            src_id = node_ids[src_idx]
            tgt_id = node_ids[tgt_idx]
            graph.add_edge(src_id, tgt_id, dependency_type='call')
        
        return graph


class HybridBridge(QObject):
    """
    HybridNode 橋接器 - 連接 Python 後端與 JavaScript 前端
    
    提供的功能：
    - analyze_project(path): 觸發完整分析流程
    - open_directory_dialog(): 開啟資料夾選擇對話框
    - load_existing_graph(): 載入已存在的圖數據
    - get_graph_stats(): 獲取統計信息
    """
    
    # 定義信號（Signal），用於向前端發送數據
    analysisProgress = pyqtSignal(str, int)  # (message, percentage)
    analysisComplete = pyqtSignal(str)  # JSON 字符串格式的圖數據
    analysisError = pyqtSignal(str)
    directorySelected = pyqtSignal(str)
    graphDataLoaded = pyqtSignal(str)  # 載入現有圖數據
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.current_worker = None
        self._graph_cache = None
        # [INFO] 儲存使用者最近一次選擇的專案目錄路徑
        # Reload 時 JS 會先查詢此屬性，再決定要呼叫 analyze_project 或 load_existing_graph
        self.current_project_path: str = ""
        logger.info("[INFO] HybridBridge 已初始化")
    
    @pyqtSlot(result=str)
    def ping(self):
        """
        測試 Bridge 連接是否正常
        
        Returns:
            JSON 字符串，包含 pong 消息和時間戳
        """
        from datetime import datetime
        response = {
            "status": "ok",
            "message": "pong",
            "timestamp": datetime.now().isoformat()
        }
        logger.info("[INFO] Bridge ping 已接收")
        return safe_json_dumps(response)
    
    @pyqtSlot(str)
    def analyze_project(self, path: str):
        """
        分析指定的 C++ 專案目錄
        
        此方法會在背景執行緒執行，避免阻塞 GUI
        分析完成後會透過 analysisComplete 信號返回結果
        
        Args:
            path: 專案目錄路徑
        """
        logger.info(f"[INFO] 開始分析專案: {path}")
        
        # 驗證路徑
        project_path = Path(path)
        if not project_path.exists():
            self.analysisError.emit(f"路徑不存在: {path}")
            return
        
        if not project_path.is_dir():
            self.analysisError.emit(f"路徑不是目錄: {path}")
            return
        
        # [INFO] 使用 quit()+wait() 而非 terminate()：
        # Windows 上 terminate() 會向執行線程發送 TerminateThread，
        # 可能導致整個進程崩潰或狀態毀損。
        # quit() 請求執行線程的事件迴圈結束，用 wait(3000) 等候至多 3 秒；
        # 若仍未結束才用 terminate() 作最後防線z。
        if self.current_worker and self.current_worker.isRunning():
            logger.warning("[WARN] 正在停止先前的分析...")
            self.current_worker.quit()
            if not self.current_worker.wait(3000):  # 等候至多 3 秒
                logger.warning("[WARN] 執行線程未在 3 秒內結束，強制終止")
                self.current_worker.terminate()
                self.current_worker.wait()
        
        # 儲存當前專案路徑，供 Reload 使用
        self.current_project_path = str(project_path)
        logger.info(f"[INFO] 已紀錄專案路徑: {self.current_project_path}")

        # 創建新的工作線程
        self.current_worker = AnalysisWorker(str(project_path))
        
        # 連接信號
        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.finished.connect(self._on_analysis_finished)
        self.current_worker.error.connect(self._on_analysis_error)
        
        # 啟動分析
        self.current_worker.start()
    
    @pyqtSlot()
    def open_directory_dialog(self):
        """
        開啟原生資料夾選擇對話框
        
        使用者選擇後會透過 directorySelected 信號返回路徑
        """
        logger.info("[INFO] 正在開啟目錄選擇對話框")
        
        directory = QFileDialog.getExistingDirectory(
            self.parent_widget,
            "選擇 C++ 專案目錄",
            "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        
        if directory:
            logger.info(f"[INFO] 已選擇目錄: {directory}")
            self.directorySelected.emit(directory)
            # [INFO] 選擇目錄後自動觸發分析，同時儲存路徑至 current_project_path
            self.analyze_project(directory)
        else:
            logger.info("[INFO] 目錄選擇已取消")

    @pyqtSlot(result=str)
    def get_last_project_path(self) -> str:
        """
        返回使用者最近一次選擇的專案目錄路徑。

        [INFO] 為何不使用 void @pyqtSlot() 的 reload_project：
        QWebChannel 的 JS proxy 只能可靠地呼叫有 result 參數的 slot，
        void slot 在部分 PyQt6 版本中無法被 JS 正確識別為可呼叫函式。
        改用此 getter 返回路徑字串，讓 JS 根據結果自行定導。
        """
        logger.info(f"[INFO] get_last_project_path: '{self.current_project_path}'")
        return self.current_project_path

    
    @pyqtSlot(str, result=str)
    def load_existing_graph(self, graph_path: str = "output/graph_data.pt"):
        """
        載入已存在的圖資料檔案。

        若檔案不存在（如首次啟動或清理後），發出空狀態訊號讓前端
        顯示「請開啟新專案」的初始畫面，嚴禁拋出未捕獲異常。
        """
        import os

        # [INFO] 前置檔案存在性檢查：
        # 直接呼叫 load_graph_data 時若檔案不存在會丟出 FileNotFoundError，
        # 過去被 except 捕獲後 emit analysisError → 前端顯示紅色錯誤 UI。
        # 改為在進入 try 前先確認，不存在則記錄 INFO 並 emit 空狀態。
        if not os.path.exists(graph_path):
            logger.info(
                f"[INFO] 未找到現有圖資料（{graph_path}），"
                "請開啟新專案進行分析。"
            )
            # emit 空的 graphDataLoaded 讓前端知道无資料可顯示（非 error）
            empty_state = safe_json_dumps({"nodes": [], "links": [], "stats": {
                "total_nodes": 0, "total_links": 0,
                "risky_nodes": 0, "risk_percentage": 0,
            }})
            self.graphDataLoaded.emit(empty_state)
            return empty_state

        try:
            logger.info(f"[INFO] 正在載入現有圖資料: {graph_path}")

            cache = load_graph_data(graph_path)

            converter = GraphDataConverter(
                cache["networkx_graph"],
                cache["pyg_data"],
                cache["labels_report"]
            )
            graph_data = converter.convert_to_react_force_graph()

            self._graph_cache = graph_data

            json_data = safe_json_dumps(graph_data)
            self.graphDataLoaded.emit(json_data)

            return json_data

        except Exception as e:
            error_msg = f"載入圖資料失敗: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")
            self.analysisError.emit(error_msg)
            return safe_json_dumps({"error": error_msg})


    
    @pyqtSlot(result=str)
    def get_graph_stats(self):
        """
        獲取當前圖的統計信息
        
        Returns:
            JSON 格式的統計數據
        """
        if self._graph_cache and "stats" in self._graph_cache:
            return safe_json_dumps(self._graph_cache["stats"])
        
        return safe_json_dumps({
            "total_nodes": 0,
            "total_links": 0,
            "risky_nodes": 0
        })
    
    @pyqtSlot(str, result=str)
    def generate_auto_tb(self, config_json_str: str) -> str:
        """
        接收前端傳來的測資設定 JSON，執行自動化 Testbench 生成與模擬
        
        工作流程：
        1. 解析前端傳來的 JSON 設定
        2. 儲存設定檔到 output/ui_stimulus_config.json
        3. 呼叫 auto_tb_generator.py 生成 Verilog Testbench
        4. 呼叫 hw_stage3_sim.py 重新執行模擬
        5. 回傳生成結果給前端
        
        參數:
            config_json_str (str): 前端組裝的完整設定 JSON 字串
            
        回傳:
            str: JSON 格式的結果字串
                成功: {"success": true, "message": "...", "testbench_path": "...", "simulation_path": "..."}
                失敗: {"success": false, "error": "錯誤訊息"}
        """
        import subprocess
        import os
        from pathlib import Path
        
        try:
            # ========== 步驟 1: 解析前端傳來的設定 ==========
            config_data = json.loads(config_json_str)
            top_module = config_data.get('top_module', 'unknown')
            logger.info(f"[Bridge] [Auto-TB] 接收到測資設定，頂層模組: {top_module}")
            
            # ========== 步驟 2: 儲存設定檔 ==========
            output_dir = Path('output')
            output_dir.mkdir(exist_ok=True)
            
            simulation_dir = Path('simulation')
            simulation_dir.mkdir(exist_ok=True)
            
            config_path = output_dir / 'ui_stimulus_config.json'
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[Bridge] [Auto-TB] 設定檔已儲存: {config_path}")
            
            # ========== 步驟 3: 呼叫 auto_tb_generator.py 生成 Testbench ==========
            tb_output_path = simulation_dir / f"{top_module}_auto_tb.v"
            
            cmd_generate = [
                'python',
                'src/auto_tb_generator.py',
                '-c', str(config_path),
                '-o', str(tb_output_path)
            ]
            
            logger.info(f"[Bridge] [Auto-TB] 執行命令: {' '.join(cmd_generate)}")
            
            result_gen = subprocess.run(
                cmd_generate,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',  # 避免 Windows PowerShell 編碼錯誤
                cwd=os.getcwd()
            )
            
            if result_gen.returncode != 0:
                error_msg = f"Testbench 生成失敗 (Exit Code {result_gen.returncode}):\n{result_gen.stderr}"
                logger.error(f"[Bridge] [Auto-TB] {error_msg}")
                return safe_json_dumps({
                    "success": False,
                    "error": error_msg
                })
            
            logger.info(f"[Bridge] [Auto-TB] Testbench 已生成: {tb_output_path}")
            logger.info(f"[Bridge] [Auto-TB] 生成器輸出:\n{result_gen.stdout}")
            
            # ========== 步驟 4: 呼叫 hw_stage3_sim.py 重新執行模擬 ==========
            # 假設原始 Verilog 檔案在 examples/sample.v
            verilog_source = Path('examples') / 'sample.v'
            
            # 如果找不到預設檔案，嘗試從設定檔中尋找
            if not verilog_source.exists():
                # 可以從 config_data 中取得原始檔案路徑（如果前端有提供）
                verilog_source = Path('examples') / f"{top_module}.v"
            
            simulation_output = output_dir / 'simulation_data.json'
            
            cmd_simulate = [
                'python',
                'src/hw_stage3_sim.py',
                str(verilog_source),
                str(tb_output_path),
                '-o', str(simulation_output)
            ]
            
            logger.info(f"[Bridge] [Auto-TB] 執行模擬命令: {' '.join(cmd_simulate)}")
            
            result_sim = subprocess.run(
                cmd_simulate,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                cwd=os.getcwd()
            )
            
            if result_sim.returncode != 0:
                error_msg = f"模擬執行失敗 (Exit Code {result_sim.returncode}):\n{result_sim.stderr}"
                logger.error(f"[Bridge] [Auto-TB] {error_msg}")
                return safe_json_dumps({
                    "success": False,
                    "error": error_msg
                })
            
            logger.info(f"[Bridge] [Auto-TB] 模擬已完成: {simulation_output}")
            logger.info(f"[Bridge] [Auto-TB] 模擬器輸出:\n{result_sim.stdout}")
            
            # ========== 步驟 5: 回傳成功結果 ==========
            response = {
                "success": True,
                "message": f"Testbench 生成與模擬成功完成！\n檔案已儲存至:\n- Testbench: {tb_output_path}\n- 模擬資料: {simulation_output}",
                "testbench_path": str(tb_output_path),
                "simulation_path": str(simulation_output),
                "config_path": str(config_path)
            }
            
            logger.info(f"[Bridge] [Auto-TB] 完成！回傳結果給前端")
            return safe_json_dumps(response)
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON 解析錯誤: {str(e)}"
            logger.error(f"[Bridge] [Auto-TB] {error_msg}")
            return safe_json_dumps({
                "success": False,
                "error": error_msg
            })
            
        except FileNotFoundError as e:
            error_msg = f"檔案或命令未找到: {str(e)}\n請確認 Python 環境與相關腳本是否存在"
            logger.error(f"[Bridge] [Auto-TB] {error_msg}")
            return safe_json_dumps({
                "success": False,
                "error": error_msg
            })
            
        except Exception as e:
            error_msg = f"執行錯誤: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"[Bridge] [Auto-TB] {error_msg}")
            return safe_json_dumps({
                "success": False,
                "error": error_msg
            })
    
    def _on_progress(self, message: str, percentage: int):
        """處理進度更新"""
        logger.info(f"[PROGRESS] {percentage}% - {message}")
        self.analysisProgress.emit(message, percentage)
    
    def _on_analysis_finished(self, graph_data: Dict[str, Any]):
        """處理分析完成"""
        logger.info("[SUCCESS] 分析已成功完成")
        
        # 快取資料
        self._graph_cache = graph_data
        
        # 轉換為 JSON 並發送
        json_data = safe_json_dumps(graph_data)
        self.analysisComplete.emit(json_data)
    
    def _on_analysis_error(self, error_message: str):
        """處理分析錯誤"""
        logger.error(f"[ERROR] 分析錯誤: {error_message}")
        self.analysisError.emit(error_message)
    
    @pyqtSlot(str, result=str)
    def run_hardware_pipeline(self, verilog_path: str) -> str:
        """
        執行硬體分析流水線（一鍵執行）
        
        前端呼叫此方法後，自動執行：
        1. Stage 1: Verilog 解析
        2. Stage 2: 圖形建立與風險檢測
        3. 複製 JSON 到前端資料夾
        
        Args:
            verilog_path: Verilog 檔案路徑（.v 或 .sv）
            
        Returns:
            JSON 字串，格式：
            {
                "success": bool,
                "message": str,
                "data": {
                    "reactflow_nodes": [...],
                    "reactflow_edges": [...]
                },
                "error": Optional[str]
            }
        """
        logger.info(f"[Bridge] [Hardware Pipeline] 開始執行硬體流水線: {verilog_path}")
        
        try:
            # 導入流水線模組
            from src.auto_hardware_pipeline import HardwarePipeline
            
            # 建立流水線實例
            pipeline = HardwarePipeline(
                output_dir="output",
                frontend_data_dir="frontend/src/data"
            )
            
            # 執行完整流水線
            result = pipeline.run_full_pipeline(verilog_path)
            
            if result["success"]:
                logger.info(f"[Bridge] [Hardware Pipeline] 執行成功")
                
                # 讀取生成的 React Flow 資料
                import json
                from pathlib import Path
                
                reactflow_json_path = Path(result["stage2_output"])
                
                if reactflow_json_path.exists():
                    with open(reactflow_json_path, 'r', encoding='utf-8') as f:
                        reactflow_data = json.load(f)
                    
                    response = {
                        "success": True,
                        "message": result["message"],
                        "data": reactflow_data,
                        "details": {
                            "stage1_output": result["stage1_output"],
                            "stage2_output": result["stage2_output"],
                            "copied_files": result["copied_files"]
                        }
                    }
                else:
                    response = {
                        "success": False,
                        "message": "流水線執行成功但找不到輸出檔案",
                        "error": f"找不到 {reactflow_json_path}"
                    }
            else:
                logger.error(f"[Bridge] [Hardware Pipeline] 執行失敗: {result.get('error')}")
                response = {
                    "success": False,
                    "message": result.get("message", "執行失敗"),
                    "error": result.get("error")
                }
            
            return safe_json_dumps(response)
            
        except ImportError as e:
            error_msg = f"無法導入流水線模組: {str(e)}\n請確認 auto_hardware_pipeline.py 是否存在"
            logger.error(f"[Bridge] [Hardware Pipeline] {error_msg}")
            return safe_json_dumps({
                "success": False,
                "error": error_msg
            })
            
        except Exception as e:
            error_msg = f"硬體流水線執行錯誤: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"[Bridge] [Hardware Pipeline] {error_msg}")
            return safe_json_dumps({
                "success": False,
                "error": error_msg
            })
    
    @pyqtSlot(result=str)
    def open_verilog_file_dialog(self) -> str:
        """
        開啟 Verilog 檔案選擇對話框
        
        Returns:
            JSON 字串，格式：
            {
                "success": bool,
                "file_path": str,
                "cancelled": bool
            }
        """
        try:
            logger.info("[Bridge] 開啟 Verilog 檔案選擇對話框")
            
            file_path, _ = QFileDialog.getOpenFileName(
                self.parent_widget,
                "選擇 Verilog 檔案",
                "",
                "Verilog Files (*.v *.sv);;All Files (*.*)"
            )
            
            if file_path:
                logger.info(f"[Bridge] 使用者選擇檔案: {file_path}")
                return safe_json_dumps({
                    "success": True,
                    "file_path": file_path,
                    "cancelled": False
                })
            else:
                logger.info("[Bridge] 使用者取消選擇")
                return safe_json_dumps({
                    "success": False,
                    "cancelled": True
                })
                
        except Exception as e:
            error_msg = f"開啟檔案對話框失敗: {str(e)}"
            logger.error(f"[Bridge] {error_msg}")
            return safe_json_dumps({
                "success": False,
                "error": error_msg
            })
