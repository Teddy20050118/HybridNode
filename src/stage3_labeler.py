"""
階段 3 弱監督標籤器
使用啟發式規則（Heuristic Rules）為圖節點打上風險標籤
"""

import json
import logging
import os
import numpy as np
import networkx as nx
import torch
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class BugLabeler:
    """
    基於啟發式規則的缺陷標籤器
    
    實作三種標記規則：
    1. 指標風險 (RISK_POINTER)
    2. 架構風險/上帝類別 (RISK_GOD_OBJECT)
    3. 外部已知 Bug (KNOWN_BUG)
    """
    
    def __init__(self, known_bugs_path: Optional[str] = None):
        """
        初始化標籤器
        
        Args:
            known_bugs_path: 已知 Bug 映射的 JSON 文件路徑
        """
        self.known_bugs_path = known_bugs_path
        self.known_bugs = {}
        
        # 標籤統計
        self.rule1_count = 0  # 指標風險
        self.rule2_count = 0  # 架構風險
        self.rule3_count = 0  # 已知 Bug
        self.total_nodes = 0
        self.positive_nodes = 0
        
        # 加載已知 Bug 列表
        if known_bugs_path and os.path.exists(known_bugs_path):
            self._load_known_bugs()
    
    def _load_known_bugs(self):
        """載入已知 Bug 映射文件"""
        try:
            with open(self.known_bugs_path, 'r', encoding='utf-8') as f:
                self.known_bugs = json.load(f)
            logger.info(f"[INFO] 已載入 {len(self.known_bugs)} 個已知 Bug 記錄")
        except Exception as e:
            logger.warning(f"[WARN] 無法載入已知 Bug 文件 {self.known_bugs_path}: {str(e)}")
            self.known_bugs = {}
    
    def _check_pointer_risk(self, node_id: str, node_data: dict) -> bool:
        """
        規則 1: 指標風險檢測
        
        條件：
        - 節點名稱或屬性包含指標相關關鍵字 (ptr, *, ->)
        - 代碼行數 > 50
        
        Args:
            node_id: 節點 ID
            node_data: 節點屬性字典
            
        Returns:
            bool: 是否為指標風險節點
        """
        # 檢查節點名稱中的指標關鍵字
        pointer_keywords = ['ptr', 'pointer', '*', '->', 'Ptr', 'POINTER']
        node_name = node_data.get('name', node_id)
        
        has_pointer_keyword = any(keyword in node_name for keyword in pointer_keywords)
        
        # 檢查代碼行數
        line_count = node_data.get('line_count', 0)
        
        # 同時滿足：有指標關鍵字 且 代碼行數 > 50
        if has_pointer_keyword and line_count > 50:
            return True
        
        # 額外檢查：如果是函數且有指標類型參數
        if node_data.get('type') == 'FunctionDecl':
            parameters = node_data.get('parameters', [])
            if isinstance(parameters, list):
                for param in parameters:
                    if isinstance(param, dict):
                        param_type = param.get('type', '')
                        if '*' in param_type or 'ptr' in param_type.lower():
                            if line_count > 50:
                                return True
        
        return False
    
    def _check_god_object_risk(self, node_id: str, out_degrees: Dict[str, int], 
                               threshold_percentile: float = 95.0) -> bool:
        """
        規則 2: 架構風險/上帝類別檢測
        
        條件：
        - 節點的出度 (out-degree) 排名在前 5%
        
        Args:
            node_id: 節點 ID
            out_degrees: 所有節點的出度字典
            threshold_percentile: 百分位閾值（默認 95%）
            
        Returns:
            bool: 是否為上帝類別
        """
        if not out_degrees:
            return False
        
        node_out_degree = out_degrees.get(node_id, 0)
        
        # 如果出度為 0，肯定不是上帝類別
        if node_out_degree == 0:
            return False
        
        # 計算出度的百分位閾值
        all_degrees = list(out_degrees.values())
        threshold = np.percentile(all_degrees, threshold_percentile)
        
        return node_out_degree >= threshold
    
    def _check_known_bug(self, node_id: str, node_data: dict) -> bool:
        """
        規則 3: 外部已知 Bug 映射
        
        條件：
        - 節點名稱在已知 Bug 列表中
        
        Args:
            node_id: 節點 ID
            node_data: 節點屬性字典
            
        Returns:
            bool: 是否為已知 Bug 節點
        """
        if not self.known_bugs:
            return False
        
        node_name = node_data.get('name', node_id)
        
        # 直接匹配節點名稱
        if node_name in self.known_bugs:
            return True
        
        # 也檢查節點 ID
        if node_id in self.known_bugs:
            return True
        
        return False
    
    def label_graph(self, graph: nx.DiGraph, verbose: bool = True) -> Dict[str, int]:
        """
        對整個圖進行標記

        Args:
            graph: NetworkX 有向圖
            verbose: 是否輸出詳細資訊

        Returns:
            Dict[str, int]: 節點 ID 到標籤的映射（0=安全, 1=風險）
        """
        if verbose:
            logger.info("[INFO] 開始執行啟發式標籤生成")

        # 初始化統計
        self.total_nodes = graph.number_of_nodes()
        self.rule1_count = 0
        self.rule2_count = 0
        self.rule3_count = 0
        self.positive_nodes = 0

        # 計算所有節點的出度
        out_degrees = dict(graph.out_degree())

        # 初始化標籤字典
        labels = {}

        # 用於詳細記錄
        rule1_nodes = set()
        rule2_nodes = set()
        rule3_nodes = set()

        # 對每個節點應用規則
        for node_id in graph.nodes():
            node_data = graph.nodes[node_id]

            is_rule1 = self._check_pointer_risk(node_id, node_data)
            is_rule2 = self._check_god_object_risk(node_id, out_degrees)
            is_rule3 = self._check_known_bug(node_id, node_data)

            if is_rule1:
                self.rule1_count += 1
                rule1_nodes.add(node_id)
            if is_rule2:
                self.rule2_count += 1
                rule2_nodes.add(node_id)
            if is_rule3:
                self.rule3_count += 1
                rule3_nodes.add(node_id)

            is_risky = is_rule1 or is_rule2 or is_rule3
            labels[node_id] = 1 if is_risky else 0

            if is_risky:
                self.positive_nodes += 1

        if verbose:
            self._print_labeling_stats(rule1_nodes, rule2_nodes, rule3_nodes)

        return labels
    
    def _print_labeling_stats(self, rule1_nodes: Set, rule2_nodes: Set, rule3_nodes: Set):
        """輸出標記統計資訊"""
        safe_count = self.total_nodes - self.positive_nodes
        logger.info("[INFO] 標記統計：")
        logger.info(f"[INFO]   總節點數：{self.total_nodes}")
        logger.info(
            f"[INFO]   風險節點數：{self.positive_nodes} "
            f"({self.positive_nodes / self.total_nodes * 100:.2f}%)"
        )
        logger.info(
            f"[INFO]   安全節點數：{safe_count} "
            f"({safe_count / self.total_nodes * 100:.2f}%)"
        )
        logger.info(f"[INFO]   規則 1 (指標風險)：{self.rule1_count} 個節點")
        if self.rule1_count > 0:
            logger.info(f"[INFO]     範例：{list(rule1_nodes)[:3]}")
        logger.info(f"[INFO]   規則 2 (架構風險)：{self.rule2_count} 個節點")
        if self.rule2_count > 0:
            logger.info(f"[INFO]     範例：{list(rule2_nodes)[:3]}")
        logger.info(f"[INFO]   規則 3 (已知 Bug)：{self.rule3_count} 個節點")
        if self.rule3_count > 0:
            logger.info(f"[INFO]     範例：{list(rule3_nodes)[:3]}")

        positive_ratio = self.positive_nodes / self.total_nodes if self.total_nodes > 0 else 0
        if positive_ratio < 0.01:
            logger.warning(
                f"[WARN] 正樣本佔比過低 ({positive_ratio * 100:.2f}%)，"
                "建議調整規則閾值或添加更多已知 Bug 記錄"
            )
        if positive_ratio > 0.5:
            logger.warning(
                f"[WARN] 正樣本佔比過高 ({positive_ratio * 100:.2f}%)，建議檢查規則是否過於寬鬆"
            )


def apply_labels(
    pyg_data,
    nx_graph: nx.DiGraph,
    known_bugs_path: Optional[str] = None,
    verbose: bool = True,
) -> tuple:
    """
    將啟發式標籤應用到 PyTorch Geometric Data 物件，並回傳包含標籤報告的純 Python 字典。

    Args:
        pyg_data: PyTorch Geometric Data 物件
        nx_graph: NetworkX 有向圖（提供出度等結構特徵）
        known_bugs_path: 已知 Bug 映射的 JSON 文件路徑（可選）
        verbose: 是否輸出詳細日誌

    Returns:
        Tuple[pyg_data, labels_report]:
            - pyg_data: 已附加 data.y 標籤張量的 PyG Data 物件
            - labels_report: 純 Python 字典，可直接 JSON 序列化
    """
    if verbose:
        logger.info("[INFO] 開始將標籤整合至 PyG Data 物件")

    # 建立標籤器
    labeler = BugLabeler(known_bugs_path=known_bugs_path)

    # 生成標籤
    labels_dict = labeler.label_graph(nx_graph, verbose=verbose)

    # 檢查 PyG Data 是否有 node_ids 屬性
    if not hasattr(pyg_data, 'node_ids'):
        raise ValueError("PyG Data 物件缺少 node_ids 屬性，無法進行標籤映射")

    # 按照 PyG Data 節點順序構建標籤張量
    labels_list = [labels_dict.get(node_id, 0) for node_id in pyg_data.node_ids]
    pyg_data.y = torch.tensor(labels_list, dtype=torch.long)

    # 驗證索引對齊
    n_x = pyg_data.x.shape[0]
    n_y = pyg_data.y.shape[0]
    n_ids = len(pyg_data.node_ids)

    if verbose:
        logger.info(f"[INFO] 索引對齊驗證：data.x={n_x}, data.y={n_y}, node_ids={n_ids}")

    if not (n_x == n_y == n_ids):
        raise ValueError(
            f"特徵矩陣、標籤向量、節點 ID 列表長度不一致："
            f"data.x={n_x}, data.y={n_y}, node_ids={n_ids}"
        )

    if verbose:
        logger.info("[INFO] 索引對齊檢查通過")

    # 統計標籤分佈
    num_positive = int((pyg_data.y == 1).sum().item())
    num_negative = int((pyg_data.y == 0).sum().item())
    total = int(pyg_data.y.shape[0])
    positive_ratio = float(num_positive / total) if total > 0 else 0.0

    if verbose:
        logger.info(
            f"[INFO] 最終標籤分佈：風險節點={num_positive} "
            f"({positive_ratio * 100:.2f}%)，安全節點={num_negative}"
        )

    # 附加統計到 pyg_data（純 Python 原生型別，避免序列化問題）
    pyg_data.num_positive = num_positive
    pyg_data.num_negative = num_negative
    pyg_data.label_stats = {
        'rule1_count': int(labeler.rule1_count),
        'rule2_count': int(labeler.rule2_count),
        'rule3_count': int(labeler.rule3_count),
        'positive_ratio': positive_ratio,
    }

    # 建構純 Python 字典作為標籤報告（JSON 序列化安全）
    labels_report: Dict[str, object] = {
        'total_nodes': total,
        'positive_nodes': num_positive,
        'negative_nodes': num_negative,
        'label_stats': pyg_data.label_stats,
        'labeled_nodes': [
            {'node_id': nid, 'label': int(pyg_data.y[i].item()), 'index': i}
            for i, nid in enumerate(pyg_data.node_ids)
        ],
    }

    logger.info("[INFO] 標籤生成完成")
    return pyg_data, labels_report


def save_labels_report(labels_report: dict, output_path: str) -> None:
    """
    將標籤報告（純 Python 字典）序列化為 JSON 文件。

    Args:
        labels_report: apply_labels 回傳的第二個值（純 Python dict）
        output_path: 輸出文件路徑
    """
    if not isinstance(labels_report, dict):
        raise TypeError(
            f"labels_report 必須為 dict，收到 {type(labels_report).__name__}"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(labels_report, f, indent=2, ensure_ascii=False)

    logger.info(f"[INFO] 標籤報告已儲存至：{output_path}")


if __name__ == "__main__":
    logger.info("[INFO] 此模組用於標籤生成，請透過 main.py 或測試腳本使用")
