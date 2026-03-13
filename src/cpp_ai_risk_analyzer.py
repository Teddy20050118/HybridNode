"""
C++ AI 風險預測分析器
結合 GNN 模型預測 + 危險函式標籤，分析可能導致專案錯誤的函式

核心功能：
1. 使用 GNN 模型（OmniGAT）對每個函式節點預測 Bug 機率
2. 結合 stage3_labeler 的危險函式標籤（指標風險、上帝類別、已知 Bug）
3. 分析呼叫鏈風險傳播（高風險函式被多處呼叫 → 風險擴散）
4. 輸出風險清單（由高至低排序），每項包含風險分數、風險原因、呼叫鏈
"""

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import torch
import networkx as nx

logger = logging.getLogger(__name__)


class CppAIRiskAnalyzer:
    """
    C++ AI 風險預測分析器

    分析維度：
    1. GNN 預測風險 - OmniGAT 模型預測的 Bug 機率
    2. 標籤規則風險 - 指標風險 / 上帝類別 / 已知 Bug
    3. 呼叫鏈傳播風險 - 高風險函式的呼叫者/被呼叫者風險擴散
    4. 結構複雜度風險 - 程式碼行數、圈複雜度、連接度
    """

    def __init__(self):
        self.nx_graph = None
        self.pyg_data = None
        self.labels_report = None
        self.node_ids = []
        self.node_names = {}
        self.predictions = None  # GNN predictions array
        self.risk_results = []

    def load_graph_data(self, graph_path: str = "output/graph_data.pt") -> bool:
        """
        載入圖資料

        Args:
            graph_path: PyG 資料檔案路徑

        Returns:
            bool: 是否成功載入
        """
        graph_file = Path(graph_path)
        if not graph_file.exists():
            logger.error(f"圖資料檔案不存在: {graph_path}")
            return False

        try:
            self.pyg_data = torch.load(graph_path, weights_only=False)
            self.node_ids = self.pyg_data.node_ids if hasattr(self.pyg_data, 'node_ids') else []
            self.node_names = self.pyg_data.node_names if hasattr(self.pyg_data, 'node_names') else {}

            # 重建 NetworkX 圖
            self.nx_graph = nx.DiGraph()
            for node_id in self.node_ids:
                attrs = {'name': self.node_names.get(node_id, node_id)}
                if hasattr(self.pyg_data, 'node_attributes'):
                    attrs.update(self.pyg_data.node_attributes.get(node_id, {}))
                self.nx_graph.add_node(node_id, **attrs)

            edge_index = self.pyg_data.edge_index
            for i in range(edge_index.shape[1]):
                src_idx = int(edge_index[0, i].item())
                tgt_idx = int(edge_index[1, i].item())
                if src_idx < len(self.node_ids) and tgt_idx < len(self.node_ids):
                    self.nx_graph.add_edge(
                        self.node_ids[src_idx],
                        self.node_ids[tgt_idx],
                        dependency_type='call'
                    )

            # 載入 labels_report
            report_path = Path("output/labels_report.json")
            if report_path.exists():
                with open(report_path, 'r', encoding='utf-8') as f:
                    self.labels_report = json.load(f)

            logger.info(f"已載入圖資料: {len(self.node_ids)} 個節點, {self.nx_graph.number_of_edges()} 條邊")
            return True

        except Exception as e:
            logger.error(f"載入圖資料失敗: {e}")
            return False

    def _run_gnn_predictions(self) -> bool:
        """
        執行 GNN 模型推論

        Returns:
            bool: 是否成功執行
        """
        model_path = Path("models/omni_gat_best.pth")
        if not model_path.exists():
            logger.info("GNN 模型不存在，將僅使用啟發式標籤進行風險評估")
            return False

        try:
            from src.stage5_inference import BugPredictor

            predictor = BugPredictor(str(model_path))
            self.predictions = predictor.predict(self.pyg_data)
            logger.info(f"GNN 推論完成，共 {len(self.predictions)} 個節點預測")
            return True

        except Exception as e:
            logger.warning(f"GNN 推論失敗: {e}")
            return False

    def _get_node_gnn_score(self, idx: int) -> float:
        """取得某節點的 GNN 預測分數"""
        if self.predictions is not None and idx < len(self.predictions):
            return float(self.predictions[idx])
        return 0.0

    def _get_node_label_info(self, node_id: str) -> Tuple[int, List[str]]:
        """
        取得某節點的標籤資訊

        Returns:
            (label, rules_matched): 標籤值和匹配的規則列表
        """
        if not self.labels_report:
            return 0, []

        risky_nodes = self.labels_report.get('risky_nodes', {})
        if node_id in risky_nodes:
            info = risky_nodes[node_id]
            return 1, info.get('rules_matched', [])

        # 也檢查 labeled_nodes 列表
        for item in self.labels_report.get('labeled_nodes', []):
            if item.get('node_id') == node_id:
                return item.get('label', 0), []

        return 0, []

    def _assess_gnn_risk(self, node_id: str, idx: int) -> Tuple[float, List[str]]:
        """
        GNN 預測風險評估

        Uses trained OmniGAT model output as primary risk signal.
        """
        score = self._get_node_gnn_score(idx)
        reasons = []

        if score >= 0.8:
            reasons.append(f"GNN 模型預測此函式 Bug 機率極高（{score:.1%}）")
        elif score >= 0.6:
            reasons.append(f"GNN 模型預測此函式 Bug 機率偏高（{score:.1%}）")
        elif score >= 0.4:
            reasons.append(f"GNN 模型預測此函式有中等 Bug 風險（{score:.1%}）")

        return score, reasons

    def _assess_label_risk(self, node_id: str) -> Tuple[float, List[str]]:
        """
        啟發式標籤風險評估

        基於 stage3_labeler 的三條規則：
        - RISK_POINTER: 指標操作 + 代碼行數 > 50
        - RISK_GOD_OBJECT: 出度排名前 5%
        - KNOWN_BUG: 已知 Bug 函式
        """
        label, rules = self._get_node_label_info(node_id)
        score = 0.0
        reasons = []

        if label == 1:
            score = 0.7
            for rule in rules:
                if 'pointer' in rule.lower() or 'RISK_POINTER' in rule:
                    reasons.append("包含指標操作且程式碼行數超過 50 行，存在記憶體安全風險")
                elif 'god' in rule.lower() or 'RISK_GOD_OBJECT' in rule:
                    reasons.append("呼叫依賴度過高（出度排名前 5%），屬於上帝函式/過度耦合")
                elif 'known' in rule.lower() or 'KNOWN_BUG' in rule:
                    reasons.append("已被標記為已知缺陷函式")
                else:
                    reasons.append(f"啟發式規則命中：{rule}")

        return score, reasons

    def _assess_propagation_risk(self, node_id: str) -> Tuple[float, List[str]]:
        """
        呼叫鏈風險傳播評估

        分析高風險函式如何透過呼叫關係影響其他函式。
        """
        score = 0.0
        reasons = []

        if self.nx_graph is None:
            return score, reasons

        # 取得此節點呼叫的所有函式（被呼叫者）
        callees = list(self.nx_graph.successors(node_id))
        # 取得所有呼叫此節點的函式（呼叫者）
        callers = list(self.nx_graph.predecessors(node_id))

        # 檢查此函式呼叫了多少高風險函式
        risky_callees = []
        for callee in callees:
            callee_label, _ = self._get_node_label_info(callee)
            callee_idx = self.node_ids.index(callee) if callee in self.node_ids else -1
            callee_gnn = self._get_node_gnn_score(callee_idx) if callee_idx >= 0 else 0.0
            if callee_label == 1 or callee_gnn >= 0.6:
                callee_name = self.node_names.get(callee, callee)
                risky_callees.append(callee_name)

        if len(risky_callees) >= 3:
            score += 0.4
            reasons.append(
                f"此函式呼叫了 {len(risky_callees)} 個高風險函式（{', '.join(risky_callees[:5])}），"
                "錯誤可能經由呼叫鏈傳播"
            )
        elif len(risky_callees) >= 1:
            score += 0.2
            reasons.append(
                f"此函式呼叫了高風險函式：{', '.join(risky_callees[:3])}"
            )

        # 檢查此高風險函式被多少函式呼叫（風險擴散範圍）
        this_label, _ = self._get_node_label_info(node_id)
        this_idx = self.node_ids.index(node_id) if node_id in self.node_ids else -1
        this_gnn = self._get_node_gnn_score(this_idx) if this_idx >= 0 else 0.0

        if (this_label == 1 or this_gnn >= 0.6) and len(callers) >= 3:
            score += 0.3
            caller_names = [self.node_names.get(c, c) for c in callers[:5]]
            reasons.append(
                f"此高風險函式被 {len(callers)} 個函式呼叫（{', '.join(caller_names)}），"
                "缺陷影響範圍較廣"
            )

        return min(score, 1.0), reasons

    def _assess_structural_risk(self, node_id: str) -> Tuple[float, List[str]]:
        """
        結構複雜度風險評估

        分析程式碼行數、圈複雜度、連接度。
        """
        score = 0.0
        reasons = []

        if self.nx_graph is None or not self.nx_graph.has_node(node_id):
            return score, reasons

        node_data = self.nx_graph.nodes[node_id]

        # 程式碼行數
        loc = node_data.get('line_count', 0)
        if loc >= 200:
            score += 0.25
            reasons.append(f"程式碼行數過多（{loc} 行），函式過於龐大，維護與測試難度高")
        elif loc >= 100:
            score += 0.1
            reasons.append(f"程式碼行數較多（{loc} 行），建議考慮拆分")

        # 圈複雜度
        complexity = node_data.get('cyclomatic_complexity', 0)
        if complexity >= 20:
            score += 0.25
            reasons.append(f"圈複雜度過高（{complexity}），邏輯分支過多，容易產生邊界錯誤")
        elif complexity >= 10:
            score += 0.1
            reasons.append(f"圈複雜度偏高（{complexity}）")

        # 連接度（入度 + 出度）
        in_deg = self.nx_graph.in_degree(node_id)
        out_deg = self.nx_graph.out_degree(node_id)
        total_deg = in_deg + out_deg

        if total_deg >= 15:
            score += 0.15
            reasons.append(f"函式連接度極高（入度 {in_deg} + 出度 {out_deg}），耦合度過高")

        return min(score, 1.0), reasons

    def _find_risk_call_chains(self, node_id: str) -> List[List[str]]:
        """
        找出經過此節點的高風險呼叫鏈

        Returns:
            呼叫鏈列表，每條為 [caller → node_id → callee → ...] 的節點 ID 列表
        """
        chains = []
        if self.nx_graph is None:
            return chains

        # 找出從此節點出發能到達的高風險節點路徑
        for target in self.nx_graph.nodes():
            if target == node_id:
                continue
            target_label, _ = self._get_node_label_info(target)
            target_idx = self.node_ids.index(target) if target in self.node_ids else -1
            target_gnn = self._get_node_gnn_score(target_idx) if target_idx >= 0 else 0.0

            if target_label == 1 or target_gnn >= 0.6:
                try:
                    for path in nx.all_simple_paths(self.nx_graph, node_id, target, cutoff=5):
                        chains.append(path)
                        if len(chains) >= 3:
                            return chains
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

        return chains

    def analyze(self) -> List[Dict[str, Any]]:
        """
        執行完整的 AI 風險預測分析

        Returns:
            風險分析結果列表（由高至低排序），每項包含：
            - node_id: 函式節點 ID
            - name: 函式名稱
            - risk_score: 綜合風險分數（0.0 ~ 1.0）
            - risk_level: 風險等級（high / medium / low）
            - reasons: 風險原因列表
            - gnn_score: GNN 模型預測分數
            - call_chains: 風險呼叫鏈（可選）
            - metrics: 函式度量資訊
        """
        if self.nx_graph is None or len(self.node_ids) == 0:
            return []

        # 嘗試執行 GNN 推論
        has_gnn = self._run_gnn_predictions()

        results = []

        for idx, node_id in enumerate(self.node_ids):
            node_data = self.nx_graph.nodes.get(node_id, {})
            node_name = self.node_names.get(node_id, node_id)

            # 多維度風險評估
            gnn_score, gnn_reasons = self._assess_gnn_risk(node_id, idx)
            label_score, label_reasons = self._assess_label_risk(node_id)
            prop_score, prop_reasons = self._assess_propagation_risk(node_id)
            struct_score, struct_reasons = self._assess_structural_risk(node_id)

            # 綜合風險分數（加權平均）
            if has_gnn:
                # 有 GNN 模型時，GNN 占主要權重
                total_score = (
                    gnn_score * 0.35
                    + label_score * 0.25
                    + prop_score * 0.25
                    + struct_score * 0.15
                )
            else:
                # 無 GNN 時，標籤與結構占更多權重
                total_score = (
                    label_score * 0.40
                    + prop_score * 0.30
                    + struct_score * 0.30
                )

            total_score = min(total_score, 1.0)
            all_reasons = gnn_reasons + label_reasons + prop_reasons + struct_reasons

            # 風險等級判定
            if total_score >= 0.5:
                risk_level = "high"
            elif total_score >= 0.25:
                risk_level = "medium"
            else:
                risk_level = "low"

            # 找出風險呼叫鏈（僅對中高風險函式）
            call_chains = []
            call_chain_strs = []
            if total_score >= 0.25:
                raw_chains = self._find_risk_call_chains(node_id)
                for chain in raw_chains:
                    chain_names = [self.node_names.get(nid, nid) for nid in chain]
                    call_chains.append(chain)
                    call_chain_strs.append(" → ".join(chain_names))

            results.append({
                "node_id": node_id,
                "name": node_name,
                "risk_score": round(total_score, 4),
                "risk_level": risk_level,
                "reasons": all_reasons if all_reasons else ["未檢測到明顯風險"],
                "gnn_score": round(gnn_score, 4),
                "call_chains": call_chains,
                "call_chain_strs": call_chain_strs,
                "metrics": {
                    "loc": node_data.get('line_count', 0),
                    "complexity": node_data.get('cyclomatic_complexity', 0),
                    "in_degree": self.nx_graph.in_degree(node_id) if self.nx_graph.has_node(node_id) else 0,
                    "out_degree": self.nx_graph.out_degree(node_id) if self.nx_graph.has_node(node_id) else 0,
                },
                "detail_scores": {
                    "gnn": round(gnn_score, 4),
                    "label": round(label_score, 4),
                    "propagation": round(prop_score, 4),
                    "structural": round(struct_score, 4),
                }
            })

        # 按風險分數由高至低排序
        results.sort(key=lambda r: r["risk_score"], reverse=True)

        self.risk_results = results
        return results

    def get_summary(self) -> Dict[str, Any]:
        """產生風險分析摘要"""
        if not self.risk_results:
            return {"total_functions": 0, "high": 0, "medium": 0, "low": 0}

        high = sum(1 for r in self.risk_results if r["risk_level"] == "high")
        medium = sum(1 for r in self.risk_results if r["risk_level"] == "medium")
        low = sum(1 for r in self.risk_results if r["risk_level"] == "low")
        has_gnn = self.predictions is not None

        return {
            "total_functions": len(self.risk_results),
            "high": high,
            "medium": medium,
            "low": low,
            "has_gnn_model": has_gnn,
            "max_risk_score": self.risk_results[0]["risk_score"] if self.risk_results else 0,
            "top_risks": self.risk_results[:5]
        }
