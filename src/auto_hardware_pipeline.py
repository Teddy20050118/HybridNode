"""
硬體分析自動化流水線
自動執行 Stage 1, 2, 3 並複製結果到前端資料夾

此模組負責：
1. 執行 hw_stage1_parser.py 解析 Verilog 檔案
2. 執行 hw_stage2_graph.py 產生圖形資料
3. 複製 JSON 檔案到前端 src/data/ 目錄
4. 提供完整的錯誤處理與日誌輸出
"""

import sys
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import traceback

# 導入硬體分析模組
from src.hw_stage1_parser import VerilogParser
from src.hw_stage2_graph import HardwareGraphAnalyzer

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class HardwarePipeline:
    """
    硬體分析自動化流水線類別
    
    封裝完整的 Verilog 分析流程，從解析到視覺化資料生成
    """
    
    def __init__(self, output_dir: str = "output", frontend_data_dir: str = "frontend/src/data"):
        """
        初始化流水線
        
        Args:
            output_dir: 輸出目錄路徑
            frontend_data_dir: 前端資料目錄路徑
        """
        self.output_dir = Path(output_dir)
        self.frontend_data_dir = Path(frontend_data_dir)
        
        # 確保目錄存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frontend_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 檔案路徑定義
        self.parsed_data_path = self.output_dir / "parsed_data.json"
        self.reactflow_data_path = self.output_dir / "reactflow_data.json"
        
        logger.info(f"[初始化] 輸出目錄: {self.output_dir}")
        logger.info(f"[初始化] 前端資料目錄: {self.frontend_data_dir}")
    
    def run_full_pipeline(self, verilog_file_path: str) -> Dict[str, Any]:
        """
        執行完整的硬體分析流水線
        
        Args:
            verilog_file_path: Verilog 來源檔案路徑
            
        Returns:
            包含執行結果的字典，格式：
            {
                "success": bool,
                "message": str,
                "stage1_output": str,
                "stage2_output": str,
                "copied_files": List[str],
                "error": Optional[str]
            }
        """
        result = {
            "success": False,
            "message": "",
            "stage1_output": "",
            "stage2_output": "",
            "copied_files": [],
            "error": None
        }
        
        try:
            logger.info("=" * 80)
            logger.info("開始執行硬體分析流水線")
            logger.info("=" * 80)
            
            # 驗證輸入檔案
            verilog_path = Path(verilog_file_path)
            if not verilog_path.exists():
                raise FileNotFoundError(f"找不到 Verilog 檔案: {verilog_file_path}")
            
            if not verilog_path.suffix.lower() in ['.v', '.sv']:
                raise ValueError(f"檔案格式錯誤: {verilog_path.suffix}，請提供 .v 或 .sv 檔案")
            
            logger.info(f"[輸入] Verilog 檔案: {verilog_path}")
            
            # ==================== Stage 1: Verilog 解析 ====================
            logger.info("\n[STAGE 1] 開始解析 Verilog 檔案...")
            stage1_result = self._run_stage1_parser(str(verilog_path))
            
            if not stage1_result["success"]:
                raise RuntimeError(f"Stage 1 失敗: {stage1_result['error']}")
            
            result["stage1_output"] = str(self.parsed_data_path)
            logger.info(f"[STAGE 1] 完成 - 輸出: {self.parsed_data_path}")
            
            # ==================== Stage 2: 圖形分析 ====================
            logger.info("\n[STAGE 2] 開始建立硬體圖形...")
            stage2_result = self._run_stage2_graph_analyzer()
            
            if not stage2_result["success"]:
                raise RuntimeError(f"Stage 2 失敗: {stage2_result['error']}")
            
            result["stage2_output"] = str(self.reactflow_data_path)
            logger.info(f"[STAGE 2] 完成 - 輸出: {self.reactflow_data_path}")
            
            # ==================== Stage 3: 複製到前端 ====================
            logger.info("\n[STAGE 3] 開始複製檔案到前端...")
            copy_result = self._copy_to_frontend()
            
            if not copy_result["success"]:
                raise RuntimeError(f"檔案複製失敗: {copy_result['error']}")
            
            result["copied_files"] = copy_result["copied_files"]
            logger.info(f"[STAGE 3] 完成 - 已複製 {len(result['copied_files'])} 個檔案")
            
            # ==================== 完成 ====================
            result["success"] = True
            result["message"] = "硬體分析流水線執行成功"
            
            logger.info("\n" + "=" * 80)
            logger.info("流水線執行成功")
            logger.info("=" * 80)
            logger.info(f"[總結] Stage 1 輸出: {result['stage1_output']}")
            logger.info(f"[總結] Stage 2 輸出: {result['stage2_output']}")
            logger.info(f"[總結] 已複製檔案: {', '.join(result['copied_files'])}")
            
            return result
            
        except Exception as e:
            error_msg = f"流水線執行失敗: {str(e)}"
            error_trace = traceback.format_exc()
            
            logger.error(f"\n[錯誤] {error_msg}")
            logger.error(f"[錯誤追蹤]\n{error_trace}")
            
            result["success"] = False
            result["error"] = error_msg
            result["message"] = error_msg
            
            return result
    
    def _run_stage1_parser(self, verilog_file: str) -> Dict[str, Any]:
        """
        執行 Stage 1: Verilog 解析器
        
        Args:
            verilog_file: Verilog 檔案路徑
            
        Returns:
            執行結果字典
        """
        try:
            logger.info(f"  > 正在解析 {verilog_file}...")
            
            # 建立解析器實例
            parser = VerilogParser()
            
            # 解析 Verilog 檔案（直接返回解析結果字典）
            parse_result = parser.parse_file(verilog_file)
            
            # 檢查是否有錯誤節點
            if parse_result.get("nodes"):
                error_nodes = [n for n in parse_result["nodes"] if n.get("type") == "error"]
                if error_nodes:
                    error_msg = error_nodes[0].get("error_message", "未知錯誤")
                    logger.warning(f"  > 解析警告: {error_msg}")
            
            # 將解析結果封裝為與 Stage 2 相容的格式
            # Stage 2 期望的格式：{"modules": [...]}
            ast_data = {
                "file": parse_result.get("file", verilog_file),
                "nodes": parse_result.get("nodes", []),
                "edges": parse_result.get("edges", []),
                "modules": []  # 將在下面填充
            }
            
            # 提取模組資訊（從節點中推斷）
            modules_found = set()
            for node in parse_result.get("nodes", []):
                module_name = node.get("module")
                if module_name and module_name != "parse_error":
                    modules_found.add(module_name)
            
            # 為每個模組建立基本結構
            for module_name in modules_found:
                module_nodes = [n for n in parse_result["nodes"] if n.get("module") == module_name]
                module_edges = [e for e in parse_result["edges"] if e.get("module") == module_name]
                
                ast_data["modules"].append({
                    "name": module_name,
                    "nodes": module_nodes,
                    "edges": module_edges
                })
            
            # 儲存為 JSON
            with open(self.parsed_data_path, 'w', encoding='utf-8') as f:
                json.dump(ast_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"  > 已儲存 AST 資料: {self.parsed_data_path}")
            logger.info(f"  > 模組數量: {len(ast_data.get('modules', []))}")
            logger.info(f"  > 節點數量: {len(ast_data.get('nodes', []))}")
            
            return {
                "success": True,
                "output_file": str(self.parsed_data_path),
                "modules_count": len(ast_data.get('modules', [])),
                "nodes_count": len(ast_data.get('nodes', []))
            }
            
        except Exception as e:
            error_msg = f"Stage 1 執行錯誤: {str(e)}"
            logger.error(f"  > {error_msg}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": error_msg
            }
    
    def _run_stage2_graph_analyzer(self) -> Dict[str, Any]:
        """
        執行 Stage 2: 圖形分析器
        
        Returns:
            執行結果字典
        """
        try:
            logger.info(f"  > 正在從 {self.parsed_data_path} 載入資料...")
            
            # 檢查 Stage 1 輸出是否存在
            if not self.parsed_data_path.exists():
                return {
                    "success": False,
                    "error": f"找不到 Stage 1 輸出檔案: {self.parsed_data_path}"
                }
            
            # 建立圖形分析器實例
            analyzer = HardwareGraphAnalyzer()
            
            # 載入 JSON 資料
            load_success = analyzer.load_from_json(str(self.parsed_data_path))
            
            if not load_success:
                return {
                    "success": False,
                    "error": "無法載入 parsed_data.json"
                }
            
            logger.info(f"  > 已載入 {len(analyzer.nodes_data)} 個節點")
            
            # 建立圖形
            analyzer.build_graph()
            logger.info(f"  > 圖形建立完成 - 節點: {analyzer.graph.number_of_nodes()}, 連線: {analyzer.graph.number_of_edges()}")
            
            # 執行風險檢測（使用正確的方法名稱）
            analyzer.run_all_detections()
            logger.info(f"  > 風險檢測完成")
            
            # 轉換為 React Flow 格式（使用正確的方法名稱）
            reactflow_data = analyzer.export_to_reactflow()
            
            # 儲存為 JSON
            with open(self.reactflow_data_path, 'w', encoding='utf-8') as f:
                json.dump(reactflow_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"  > 已儲存 React Flow 資料: {self.reactflow_data_path}")
            logger.info(f"  > React Flow 節點數: {len(reactflow_data.get('reactflow_nodes', []))}")
            logger.info(f"  > React Flow 連線數: {len(reactflow_data.get('reactflow_edges', []))}")
            
            return {
                "success": True,
                "output_file": str(self.reactflow_data_path),
                "nodes_count": len(reactflow_data.get('reactflow_nodes', [])),
                "edges_count": len(reactflow_data.get('reactflow_edges', []))
            }
            
        except Exception as e:
            error_msg = f"Stage 2 執行錯誤: {str(e)}"
            logger.error(f"  > {error_msg}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": error_msg
            }
    
    def _copy_to_frontend(self) -> Dict[str, Any]:
        """
        複製 JSON 檔案到前端資料目錄
        
        Returns:
            複製結果字典
        """
        copied_files = []
        
        try:
            # 定義要複製的檔案
            files_to_copy = [
                ("parsed_data.json", self.parsed_data_path),
                ("reactflow_data.json", self.reactflow_data_path)
            ]
            
            # 逐一複製檔案
            for filename, source_path in files_to_copy:
                if not source_path.exists():
                    logger.warning(f"  > 警告: 找不到 {source_path}，跳過複製")
                    continue
                
                dest_path = self.frontend_data_dir / filename
                
                # 強制覆蓋複製
                shutil.copy2(source_path, dest_path)
                
                logger.info(f"  > 已複製: {filename} -> {dest_path}")
                copied_files.append(filename)
            
            if len(copied_files) == 0:
                return {
                    "success": False,
                    "error": "沒有檔案被複製"
                }
            
            return {
                "success": True,
                "copied_files": copied_files
            }
            
        except Exception as e:
            error_msg = f"檔案複製錯誤: {str(e)}"
            logger.error(f"  > {error_msg}")
            logger.error(traceback.format_exc())
            
            return {
                "success": False,
                "error": error_msg
            }
    
    def validate_output_files(self) -> Dict[str, bool]:
        """
        驗證輸出檔案是否存在且有效
        
        Returns:
            驗證結果字典
        """
        validation = {
            "parsed_data.json": False,
            "reactflow_data.json": False,
            "frontend_parsed_data.json": False,
            "frontend_reactflow_data.json": False
        }
        
        # 檢查 output/ 目錄
        if self.parsed_data_path.exists():
            try:
                with open(self.parsed_data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'modules' in data:
                        validation["parsed_data.json"] = True
            except:
                pass
        
        if self.reactflow_data_path.exists():
            try:
                with open(self.reactflow_data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'reactflow_nodes' in data:
                        validation["reactflow_data.json"] = True
            except:
                pass
        
        # 檢查 frontend/src/data/ 目錄
        frontend_parsed = self.frontend_data_dir / "parsed_data.json"
        if frontend_parsed.exists():
            try:
                with open(frontend_parsed, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'modules' in data:
                        validation["frontend_parsed_data.json"] = True
            except:
                pass
        
        frontend_reactflow = self.frontend_data_dir / "reactflow_data.json"
        if frontend_reactflow.exists():
            try:
                with open(frontend_reactflow, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'reactflow_nodes' in data:
                        validation["frontend_reactflow_data.json"] = True
            except:
                pass
        
        return validation


def run_hardware_analysis(verilog_file: str, output_dir: str = "output", 
                          frontend_data_dir: str = "frontend/src/data") -> Dict[str, Any]:
    """
    執行硬體分析的便捷函式
    
    Args:
        verilog_file: Verilog 檔案路徑
        output_dir: 輸出目錄
        frontend_data_dir: 前端資料目錄
        
    Returns:
        執行結果字典
    """
    pipeline = HardwarePipeline(output_dir, frontend_data_dir)
    return pipeline.run_full_pipeline(verilog_file)


if __name__ == "__main__":
    """命令列執行範例"""
    
    if len(sys.argv) < 2:
        print("使用方式: python -m src.auto_hardware_pipeline <verilog_file>")
        print("範例: python -m src.auto_hardware_pipeline examples/sample.v")
        sys.exit(1)
    
    verilog_file = sys.argv[1]
    
    # 執行流水線
    result = run_hardware_analysis(verilog_file)
    
    # 輸出結果
    print("\n" + "=" * 80)
    print("執行結果")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 設定退出代碼
    sys.exit(0 if result["success"] else 1)
