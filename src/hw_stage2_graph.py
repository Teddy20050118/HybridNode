"""
硬體圖形分析器 - 第二階段
使用 NetworkX 建立有向圖，執行硬體風險特徵檢測，並轉換為 React Flow 格式

此模組負責：
1. 從 Stage 1 的 JSON 輸出建立 NetworkX 有向圖
2. 執行硬體設計風險檢測（位元寬度不符、賦值模式錯誤、缺少重置訊號、組合邏輯迴圈）
3. 為節點生成佈局座標
4. 轉換為 React Flow 可直接渲染的資料格式
"""

import os
import sys
import json
from typing import Dict, List, Any, Tuple, Set, Optional
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    print("錯誤：無法導入 NetworkX 模組，請先安裝 networkx")
    print("安裝指令：pip install networkx")
    sys.exit(1)


class HardwareGraphAnalyzer:
    """
    硬體圖形分析器
    建立 NetworkX 圖形，執行風險檢測，並輸出 React Flow 格式
    """
    
    def __init__(self):
        """初始化分析器"""
        self.graph = nx.DiGraph()  # 有向圖
        self.nodes_data = []  # 原始節點資料
        self.edges_data = []  # 原始連線資料
        self.source_file = None  # 來源檔案
        
        # 風險統計
        self.risk_stats = {
            "width_mismatch": 0,
            "assignment_error": 0,
            "missing_reset": 0,
            "comb_loop": 0,
            "unused": 0
        }
    
    def load_from_json(self, json_path: str) -> bool:
        """
        從 JSON 檔案載入解析資料
        
        Args:
            json_path: JSON 檔案路徑
            
        Returns:
            載入成功回傳 True，失敗回傳 False
        """
        print(f"\n正在載入 JSON 檔案：{json_path}")
        
        if not os.path.isfile(json_path):
            print(f"錯誤：檔案不存在 - {json_path}")
            return False
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 處理單一檔案或多檔案格式
            if isinstance(data, list):
                # 多檔案格式，合併所有節點與連線
                print(f"偵測到多檔案格式，共 {len(data)} 個檔案")
                
                for file_data in data:
                    # 檢查是否包含舊版 error 欄位（轉換為警告節點）
                    if "error" in file_data:
                        error_msg = file_data.get('error', '未知錯誤')
                        file_path = file_data.get('file', 'unknown')
                        print(f"警告：檔案包含解析錯誤，將轉換為警告節點 - {file_path}")
                        
                        # 建立虛擬警告節點
                        warning_node = {
                            "id": f"ERROR_{file_path.replace('/', '_').replace('\\', '_')}",
                            "type": "error",
                            "width": 1,
                            "module": "parse_error",
                            "error_message": error_msg
                        }
                        self.nodes_data.append(warning_node)
                        continue
                    
                    self.nodes_data.extend(file_data.get("nodes", []))
                    self.edges_data.extend(file_data.get("edges", []))
                    
            elif isinstance(data, dict):
                # 單一檔案格式
                # 檢查是否包含舊版 error 欄位（轉換為警告節點）
                if "error" in data:
                    error_msg = data.get('error', '未知錯誤')
                    file_path = data.get('file', 'unknown')
                    print(f"警告：檔案包含解析錯誤，將轉換為警告節點 - {file_path}")
                    
                    # 建立虛擬警告節點
                    warning_node = {
                        "id": f"ERROR_{file_path.replace('/', '_').replace('\\', '_')}",
                        "type": "error",
                        "width": 1,
                        "module": "parse_error",
                        "error_message": error_msg
                    }
                    self.nodes_data.append(warning_node)
                    self.source_file = file_path
                else:
                    self.source_file = data.get("file")
                    self.nodes_data = data.get("nodes", [])
                    self.edges_data = data.get("edges", [])
            else:
                print(f"錯誤：不支援的 JSON 格式")
                return False
            
            print(f"載入成功：{len(self.nodes_data)} 個節點，{len(self.edges_data)} 條連線")
            return True
            
        except json.JSONDecodeError as e:
            print(f"錯誤：JSON 格式錯誤 - {str(e)}")
            return False
        except Exception as e:
            print(f"錯誤：載入檔案時發生異常 - {str(e)}")
            return False
    
    def build_graph(self):
        """
        建立 NetworkX 有向圖
        將節點與連線資料寫入圖形，保留所有屬性
        使用 module::id 作為複合鍵，避免不同模組間同名節點互相覆蓋
        """
        print("\n開始建立 NetworkX 圖形...")
        
        # 清空現有圖形
        self.graph.clear()
        
        # 加入節點（使用 module::id 複合鍵，去重同模組內 output/reg 重複宣告）
        seen_keys = {}  # {composite_key: node_type}  用於去重
        for node in self.nodes_data:
            node_id = node.get("id")
            module = node.get("module", "unknown")
            if not node_id:
                print(f"警告：跳過無 ID 的節點 - {node}")
                continue
            
            composite_key = f"{module}::{node_id}"
            node_type = node.get("type", "unknown")
            
            # 去重：同模組同名節點只保留一個，優先保留 reg 類型
            if composite_key in seen_keys:
                existing_type = seen_keys[composite_key]
                if node_type == "reg" and existing_type != "reg":
                    # 新的是 reg，覆蓋舊的
                    pass
                else:
                    # 跳過重複節點
                    continue
            seen_keys[composite_key] = node_type
            
            # 將所有屬性加入節點，使用複合鍵
            self.graph.add_node(
                composite_key,
                original_id=node_id,                      # 保留原始 ID
                node_type=node_type,
                width=node.get("width", 1),
                msb=node.get("msb"),
                lsb=node.get("lsb"),
                module=module,
                target_module=node.get("target_module"),
                risk=None  # 初始化風險屬性
            )
        
        # 建立 node_id → modules 查詢表（一個 id 可能屬於多個模組）
        node_to_modules = {}
        for node in self.nodes_data:
            nid = node.get("id")
            mod = node.get("module")
            if nid and mod:
                if nid not in node_to_modules:
                    node_to_modules[nid] = set()
                node_to_modules[nid].add(mod)
        
        # 加入連線（使用 module::from / module::to 複合鍵）
        for edge in self.edges_data:
            source = edge.get("from")
            target = edge.get("to")
            module = edge.get("module")
            
            if not source or not target:
                print(f"警告：跳過無效的連線 - {edge}")
                continue
            
            # 若 edge 無 module（如 port_map），從節點推斷所屬模組
            if not module:
                src_mods = node_to_modules.get(source, set())
                tgt_mods = node_to_modules.get(target, set())
                # 優先取兩者共同的模組
                common = src_mods & tgt_mods
                if common:
                    module = next(iter(common))
                elif src_mods:
                    module = next(iter(src_mods))
                elif tgt_mods:
                    module = next(iter(tgt_mods))
                else:
                    module = "unknown"
            
            source_key = f"{module}::{source}"
            target_key = f"{module}::{target}"
            
            # 確保節點存在（防止連線指向不存在的節點）
            if source_key not in self.graph:
                print(f"警告：來源節點不存在，自動建立 - {source_key}")
                self.graph.add_node(source_key, original_id=source, node_type="unknown", width=1, module=module)
            
            if target_key not in self.graph:
                print(f"警告：目標節點不存在，自動建立 - {target_key}")
                self.graph.add_node(target_key, original_id=target, node_type="unknown", width=1, module=module)
            
            # 將所有屬性加入連線
            self.graph.add_edge(
                source_key,
                target_key,
                assign_type=edge.get("assign_type", "unknown"),
                logic_type=edge.get("logic_type", "combinational"),
                sensitivity=edge.get("sensitivity", []),
                module=module,
                target_module=edge.get("target_module"),
                risk=None,  # 初始化風險屬性
                animated=False,
                style={}
            )
        
        print(f"圖形建立完成：{self.graph.number_of_nodes()} 個節點，{self.graph.number_of_edges()} 條連線")
    
    def detect_width_mismatch(self):
        """
        Rule 1: 偵測位元寬度不符
        比較每條連線的來源與目標節點的寬度，若不相等則標記為風險
        """
        print("\n執行 Rule 1：偵測位元寬度不符...")
        count = 0
        
        for source, target, edge_data in self.graph.edges(data=True):
            source_width = self.graph.nodes[source].get("width", 1)
            target_width = self.graph.nodes[target].get("width", 1)
            
            if source_width != target_width:
                # 標記連線風險
                edge_data["risk"] = "width_mismatch"
                edge_data["style"] = {
                    "stroke": "#FF9900",
                    "strokeWidth": 2
                }
                count += 1
                
                print(f"  發現寬度不符：{source} ({source_width}-bit) -> {target} ({target_width}-bit)")
        
        self.risk_stats["width_mismatch"] = count
        print(f"完成：共發現 {count} 處位元寬度不符")
    
    def detect_assignment_errors(self):
        """
        Rule 2: 偵測賦值模式錯誤
        時序邏輯應使用非阻塞賦值，組合邏輯應使用阻塞賦值
        """
        print("\n執行 Rule 2：偵測賦值模式錯誤...")
        count = 0
        
        for source, target, edge_data in self.graph.edges(data=True):
            logic_type = edge_data.get("logic_type", "combinational")
            assign_type = edge_data.get("assign_type", "unknown")
            
            is_error = False
            
            # 時序邏輯使用阻塞賦值是錯誤的
            if logic_type == "sequential" and assign_type == "blocking":
                is_error = True
                print(f"  發現賦值錯誤：時序邏輯使用阻塞賦值 - {source} -> {target}")
            
            # 組合邏輯使用非阻塞賦值也是錯誤的
            elif logic_type == "combinational" and assign_type == "nonblocking":
                is_error = True
                print(f"  發現賦值錯誤：組合邏輯使用非阻塞賦值 - {source} -> {target}")
            
            if is_error:
                # 標記目標節點風險
                current_risk = self.graph.nodes[target].get("risk")
                if current_risk:
                    self.graph.nodes[target]["risk"] = f"{current_risk}, assignment_error"
                else:
                    self.graph.nodes[target]["risk"] = "assignment_error"
                count += 1
        
        self.risk_stats["assignment_error"] = count
        print(f"完成：共發現 {count} 處賦值模式錯誤")
    
    def detect_missing_reset(self):
        """
        Rule 3: 偵測缺少重置訊號
        時序邏輯應該包含重置訊號（rst, rst_n, reset, reset_n 等）
        """
        print("\n執行 Rule 3：偵測缺少重置訊號...")
        count = 0
        
        # 重置訊號的常見命名
        reset_keywords = ["rst", "reset", "rst_n", "reset_n", "rstn", "resetn"]
        
        for node in self.graph.nodes():
            # 檢查該節點是否被時序邏輯驅動
            has_sequential_input = False
            sensitivity_signals = set()
            
            for predecessor in self.graph.predecessors(node):
                edge_data = self.graph.edges[predecessor, node]
                logic_type = edge_data.get("logic_type", "combinational")
                
                if logic_type == "sequential":
                    has_sequential_input = True
                    sensitivity = edge_data.get("sensitivity", [])
                    sensitivity_signals.update(sensitivity)
            
            # 如果有時序輸入，檢查是否包含重置訊號
            if has_sequential_input:
                has_reset = any(
                    any(keyword in sig.lower() for keyword in reset_keywords)
                    for sig in sensitivity_signals
                )
                
                if not has_reset:
                    # 標記節點風險
                    current_risk = self.graph.nodes[node].get("risk")
                    if current_risk:
                        self.graph.nodes[node]["risk"] = f"{current_risk}, missing_reset"
                    else:
                        self.graph.nodes[node]["risk"] = "missing_reset"
                    count += 1
                    
                    print(f"  發現缺少重置：{node} (敏感訊號: {sensitivity_signals})")
        
        self.risk_stats["missing_reset"] = count
        print(f"完成：共發現 {count} 個節點缺少重置訊號")
    
    def detect_combinational_loops(self):
        """
        Rule 4: 偵測組合邏輯迴圈
        組合邏輯不應該形成迴圈（會導致不穩定的電路）
        """
        print("\n執行 Rule 4：偵測組合邏輯迴圈...")
        
        # 建立組合邏輯子圖
        combinational_edges = [
            (u, v) for u, v, data in self.graph.edges(data=True)
            if data.get("logic_type") == "combinational" or 
               data.get("assign_type") == "continuous"
        ]
        
        if not combinational_edges:
            print("無組合邏輯連線，跳過迴圈檢測")
            return
        
        comb_subgraph = self.graph.edge_subgraph(combinational_edges).copy()
        print(f"組合邏輯子圖：{comb_subgraph.number_of_nodes()} 個節點，{comb_subgraph.number_of_edges()} 條連線")
        
        # 尋找簡單迴圈
        try:
            cycles = list(nx.simple_cycles(comb_subgraph))
            
            if cycles:
                print(f"發現 {len(cycles)} 個組合邏輯迴圈：")
                
                for i, cycle in enumerate(cycles, 1):
                    print(f"  迴圈 {i}: {' -> '.join(cycle)} -> {cycle[0]}")
                    
                    # 標記迴圈中的所有連線
                    for j in range(len(cycle)):
                        source = cycle[j]
                        target = cycle[(j + 1) % len(cycle)]
                        
                        if self.graph.has_edge(source, target):
                            edge_data = self.graph.edges[source, target]
                            edge_data["risk"] = "comb_loop"
                            edge_data["animated"] = True
                            edge_data["style"] = {
                                "stroke": "#FF0000",
                                "strokeWidth": 3
                            }
                
                self.risk_stats["comb_loop"] = len(cycles)
                print(f"完成：共發現 {len(cycles)} 個組合邏輯迴圈")
            else:
                print("完成：未發現組合邏輯迴圈")
                
        except Exception as e:
            print(f"警告：迴圈偵測時發生錯誤 - {str(e)}")
    
    def detect_unused_variables(self):
        """
        Rule 5: 偵測宣告但未使用的變數
        若一個節點既無輸入邊也無輸出邊（度數為 0），標記為 unused
        排除 submodule 類型的節點（它們的連線可能在 port_map 中表達）
        """
        print("\n執行 Rule 5：偵測未使用的變數...")
        count = 0
        
        for node in self.graph.nodes():
            node_data = self.graph.nodes[node]
            node_type = node_data.get("node_type", "unknown")
            
            # 跳過 submodule 節點（它們的連線結構不同）
            if node_type == "submodule":
                continue
            
            in_degree = self.graph.in_degree(node)
            out_degree = self.graph.out_degree(node)
            
            if in_degree == 0 and out_degree == 0:
                # 標記為 unused 風險
                current_risk = node_data.get("risk")
                if current_risk:
                    node_data["risk"] = f"{current_risk}, unused"
                else:
                    node_data["risk"] = "unused"
                count += 1
                original_id = node_data.get("original_id", node)
                print(f"  發現未使用的變數：{original_id} (模組: {node_data.get('module', '?')})")
        
        self.risk_stats["unused"] = count
        print(f"完成：共發現 {count} 個未使用的變數")
    
    def run_all_detections(self):
        """
        執行所有風險檢測規則
        """
        print("\n" + "=" * 60)
        print("開始執行硬體風險檢測")
        print("=" * 60)
        
        self.detect_width_mismatch()
        self.detect_assignment_errors()
        self.detect_missing_reset()
        self.detect_combinational_loops()
        self.detect_unused_variables()
        
        print("\n" + "=" * 60)
        print("風險檢測完成 - 統計摘要")
        print("=" * 60)
        for risk_type, count in self.risk_stats.items():
            print(f"  {risk_type}: {count}")
    
    def generate_layout(self, layout_algorithm: str = "spring", scale: float = 500.0) -> Dict[str, Tuple[float, float]]:
        """
        為圖形節點生成佈局座標
        
        Args:
            layout_algorithm: 佈局演算法（spring, multipartite, circular, shell）
            scale: 座標縮放比例
            
        Returns:
            節點位置字典 {node_id: (x, y)}
        """
        print(f"\n生成佈局（演算法：{layout_algorithm}，縮放：{scale}）...")
        
        if self.graph.number_of_nodes() == 0:
            print("警告：圖形為空，無法生成佈局")
            return {}
        
        try:
            if layout_algorithm == "multipartite":
                # 根據節點類型分層
                # Input -> Wire/Reg -> Output
                for node in self.graph.nodes():
                    node_type = self.graph.nodes[node].get("node_type", "unknown")
                    if node_type in ["input", "inout"]:
                        self.graph.nodes[node]["subset"] = 0
                    elif node_type == "output":
                        self.graph.nodes[node]["subset"] = 2
                    else:
                        self.graph.nodes[node]["subset"] = 1
                
                pos = nx.multipartite_layout(self.graph, scale=scale)
                
            elif layout_algorithm == "circular":
                pos = nx.circular_layout(self.graph, scale=scale)
                
            elif layout_algorithm == "shell":
                pos = nx.shell_layout(self.graph, scale=scale)
                
            else:  # spring (default)
                pos = nx.spring_layout(
                    self.graph,
                    k=2.0,  # 節點間距
                    iterations=50,
                    scale=scale,
                    seed=42  # 固定隨機種子以確保結果可重現
                )
            
            print(f"佈局生成完成：{len(pos)} 個節點")
            return pos
            
        except Exception as e:
            print(f"錯誤：生成佈局時發生異常 - {str(e)}")
            # 降級到簡單的線性佈局
            print("使用降級佈局（線性排列）...")
            pos = {}
            for i, node in enumerate(self.graph.nodes()):
                pos[node] = (i * 100.0, 0.0)
            return pos
    
    def export_to_reactflow(self, layout_algorithm: str = "spring", scale: float = 500.0) -> Dict[str, Any]:
        """
        轉換為 React Flow 格式
        
        Args:
            layout_algorithm: 佈局演算法
            scale: 座標縮放比例
            
        Returns:
            包含 reactflow_nodes 與 reactflow_edges 的字典
        """
        print("\n轉換為 React Flow 格式...")
        
        # 生成佈局
        pos = self.generate_layout(layout_algorithm, scale)
        
        reactflow_nodes = []
        reactflow_edges = []
        
        # 轉換節點
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            position = pos.get(node_id, (0, 0))
            original_id = node_data.get("original_id", node_id)
            
            # 建立 React Flow 節點
            rf_node = {
                "id": node_id,
                "position": {
                    "x": float(position[0]),
                    "y": float(position[1])
                },
                "data": {
                    "label": original_id,
                    "originalId": original_id,
                    "type": node_data.get("node_type", "unknown"),
                    "width": node_data.get("width", 1),
                    "module": node_data.get("module"),
                    "target_module": node_data.get("target_module")
                },
                "type": "customNode"  # 使用自訂節點類型
            }
            
            # 加入風險資訊（如果有）
            if node_data.get("risk"):
                rf_node["data"]["risk"] = node_data["risk"]
            
            # 加入 MSB/LSB 資訊（如果有）
            if node_data.get("msb") is not None:
                rf_node["data"]["msb"] = node_data["msb"]
                rf_node["data"]["lsb"] = node_data["lsb"]
            
            reactflow_nodes.append(rf_node)
        
        # 轉換連線
        edge_id_counter = 0
        for source, target, edge_data in self.graph.edges(data=True):
            edge_id = f"{source}-{target}-{edge_id_counter}"
            edge_id_counter += 1
            
            # 從複合鍵取得原始 ID
            source_original = self.graph.nodes[source].get("original_id", source)
            target_original = self.graph.nodes[target].get("original_id", target)
            
            # 建立 React Flow 連線
            rf_edge = {
                "id": edge_id,
                "source": source,
                "target": target,
                "animated": edge_data.get("animated", False),
                "data": {
                    "logic_type": edge_data.get("logic_type", "combinational"),
                    "assign_type": edge_data.get("assign_type", "unknown"),
                    "originalSource": source_original,
                    "originalTarget": target_original
                }
            }
            
            # 加入樣式（如果有）
            if edge_data.get("style"):
                rf_edge["style"] = edge_data["style"]
            
            # 加入風險資訊（如果有）
            if edge_data.get("risk"):
                rf_edge["data"]["risk"] = edge_data["risk"]
            
            # 加入敏感訊號資訊（如果有）
            if edge_data.get("sensitivity"):
                rf_edge["data"]["sensitivity"] = edge_data["sensitivity"]
            
            reactflow_edges.append(rf_edge)
        
        print(f"轉換完成：{len(reactflow_nodes)} 個節點，{len(reactflow_edges)} 條連線")
        
        return {
            "reactflow_nodes": reactflow_nodes,
            "reactflow_edges": reactflow_edges,
            "risk_stats": self.risk_stats,
            "metadata": {
                "source_file": self.source_file,
                "total_nodes": len(reactflow_nodes),
                "total_edges": len(reactflow_edges),
                "layout_algorithm": layout_algorithm,
                "scale": scale
            }
        }
    
    def analyze(self, json_path: str, layout_algorithm: str = "spring", scale: float = 500.0) -> Optional[Dict[str, Any]]:
        """
        完整分析流程
        
        Args:
            json_path: 輸入 JSON 檔案路徑
            layout_algorithm: 佈局演算法
            scale: 座標縮放比例
            
        Returns:
            React Flow 格式的結果，若失敗則回傳 None
        """
        # 載入 JSON
        if not self.load_from_json(json_path):
            return None
        
        # 建立圖形
        if len(self.nodes_data) == 0:
            print("警告：無節點資料，無法建立圖形")
            return None
        
        self.build_graph()
        
        # 執行風險檢測
        self.run_all_detections()
        
        # 轉換為 React Flow 格式
        result = self.export_to_reactflow(layout_algorithm, scale)
        
        return result


def main():
    """
    主函式：提供命令列介面
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="硬體圖形分析器 - 建立圖形、執行風險檢測、輸出 React Flow 格式"
    )
    parser.add_argument(
        "input",
        help="輸入 JSON 檔案路徑（來自 Stage 1 的解析結果）"
    )
    parser.add_argument(
        "-o", "--output",
        help="輸出 JSON 檔案路徑（React Flow 格式）",
        default="output/reactflow_data.json"
    )
    parser.add_argument(
        "-l", "--layout",
        choices=["spring", "multipartite", "circular", "shell"],
        default="spring",
        help="佈局演算法（預設：spring）"
    )
    parser.add_argument(
        "-s", "--scale",
        type=float,
        default=500.0,
        help="座標縮放比例（預設：500.0）"
    )
    
    args = parser.parse_args()
    
    # 建立分析器
    analyzer = HardwareGraphAnalyzer()
    
    # 執行分析
    result = analyzer.analyze(
        json_path=args.input,
        layout_algorithm=args.layout,
        scale=args.scale
    )
    
    if result is None:
        print("\n分析失敗")
        sys.exit(1)
    
    # 儲存結果
    try:
        # 確保輸出目錄存在
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"已建立輸出目錄：{output_dir}")
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n結果已儲存至：{args.output}")
        print("\n分析完成！")
        
    except Exception as e:
        print(f"\n錯誤：無法儲存結果檔案 - {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
