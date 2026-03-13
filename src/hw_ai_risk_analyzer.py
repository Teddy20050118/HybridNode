"""
硬體 AI 風險預測分析器
使用 AI 語義分析 + 圖結構分析，對電路邏輯路徑進行風險評估

核心功能：
1. 接收使用者提供的電路功能描述
2. 分析 parsed_data / reactflow_data 中的邏輯路徑
3. 使用 sentence-transformers 進行語義比對，判斷電路是否符合預期功能
4. 對邏輯路徑進行多維度風險評估（結構風險、邏輯風險、語義風險）
5. 輸出風險清單（由高至低排序），每條記錄包含路徑、風險分數、風險原因
"""

import json
import os
import math
from typing import Dict, List, Any, Optional, Tuple, Set
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    nx = None

# 嘗試載入 sentence-transformers（用於語義分析）
_sentence_model = None

def _get_sentence_model():
    """延遲載入 SentenceTransformer 模型（避免啟動時阻塞）"""
    global _sentence_model
    if _sentence_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception:
            _sentence_model = None
    return _sentence_model


def cosine_similarity(vec_a, vec_b) -> float:
    """計算兩個向量的餘弦相似度"""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class HardwareAIRiskAnalyzer:
    """
    硬體 AI 風險預測分析器

    分析維度：
    1. 結構風險 - 組合迴圈、扇出過高、路徑過長
    2. 賦值風險 - 時序/組合邏輯賦值不當
    3. 寬度風險 - 位元寬度不匹配
    4. 語義風險 - 電路行為與使用者描述不符
    """

    def __init__(self):
        self.graph = None  # NetworkX DiGraph
        self.nodes_data = []
        self.edges_data = []
        self.reactflow_data = None
        self.risk_results = []

    def load_data(self, parsed_json_path: str = None, reactflow_json_path: str = None) -> bool:
        """
        載入分析所需資料

        Args:
            parsed_json_path: Stage 1 解析結果 JSON 路徑
            reactflow_json_path: Stage 2 React Flow JSON 路徑

        Returns:
            bool: 是否成功載入
        """
        # 優先使用 reactflow 資料
        if reactflow_json_path and os.path.isfile(reactflow_json_path):
            with open(reactflow_json_path, 'r', encoding='utf-8') as f:
                self.reactflow_data = json.load(f)
            rf_nodes = self.reactflow_data.get("reactflow_nodes", [])
            rf_edges = self.reactflow_data.get("reactflow_edges", [])
            self._build_graph_from_reactflow(rf_nodes, rf_edges)
            return True

        if parsed_json_path and os.path.isfile(parsed_json_path):
            with open(parsed_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    self.nodes_data.extend(item.get("nodes", []))
                    self.edges_data.extend(item.get("edges", []))
            elif isinstance(data, dict):
                self.nodes_data = data.get("nodes", [])
                self.edges_data = data.get("edges", [])
            self._build_graph_from_parsed()
            return True

        return False

    def _build_graph_from_reactflow(self, rf_nodes: List[Dict], rf_edges: List[Dict]):
        """從 React Flow 資料建立 NetworkX 圖"""
        self.graph = nx.DiGraph()
        for n in rf_nodes:
            nid = n.get("id", "")
            ndata = n.get("data", {})
            self.graph.add_node(nid, **ndata)
        for e in rf_edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            edata = e.get("data", {})
            self.graph.add_edge(src, tgt, **edata)

    def _build_graph_from_parsed(self):
        """從 parsed_data 建立 NetworkX 圖"""
        self.graph = nx.DiGraph()
        for n in self.nodes_data:
            nid = n.get("id", "")
            mod = n.get("module", "unknown")
            key = f"{mod}::{nid}"
            self.graph.add_node(key, **n, original_id=nid)
        for e in self.edges_data:
            src = e.get("from", "")
            tgt = e.get("to", "")
            mod = e.get("module", "unknown")
            self.graph.add_edge(f"{mod}::{src}", f"{mod}::{tgt}", **e)

    # ====================================================================
    # 路徑提取
    # ====================================================================

    def extract_logic_paths(self) -> List[Dict[str, Any]]:
        """
        提取所有有意義的邏輯路徑（input → output / input → reg / reg → output）

        Returns:
            路徑列表，每條路徑包含 nodes, edges, length, modules
        """
        if self.graph is None or self.graph.number_of_nodes() == 0:
            return []

        # 找出所有 input / output / reg 節點
        inputs = []
        outputs = []
        regs = []

        for nid, ndata in self.graph.nodes(data=True):
            ntype = ndata.get("type", ndata.get("node_type", "")).lower()
            if ntype == "input":
                inputs.append(nid)
            elif ntype == "output":
                outputs.append(nid)
            elif ntype == "reg":
                regs.append(nid)

        # 終點集合 = output ∪ reg
        sinks = set(outputs + regs)
        # 起點集合 = input ∪ reg
        sources = set(inputs + regs)

        paths = []
        visited_pairs = set()

        for src in sources:
            for sink in sinks:
                if src == sink:
                    continue
                pair = (src, sink)
                if pair in visited_pairs:
                    continue
                visited_pairs.add(pair)

                try:
                    # 使用 nx.all_simple_paths 限制長度以避免指數爆炸
                    for path_nodes in nx.all_simple_paths(self.graph, src, sink, cutoff=15):
                        path_edges = []
                        for i in range(len(path_nodes) - 1):
                            edata = self.graph.get_edge_data(path_nodes[i], path_nodes[i + 1])
                            path_edges.append(edata or {})

                        # 收集路徑涉及的模組
                        modules = set()
                        for nid in path_nodes:
                            mod = self.graph.nodes[nid].get("module", "")
                            if mod:
                                modules.add(mod)

                        # 取得可讀名稱
                        readable_names = []
                        for nid in path_nodes:
                            nd = self.graph.nodes[nid]
                            readable_names.append(nd.get("label", nd.get("original_id", nid)))

                        paths.append({
                            "node_ids": path_nodes,
                            "node_names": readable_names,
                            "edges": path_edges,
                            "length": len(path_nodes),
                            "modules": list(modules),
                            "path_str": " → ".join(readable_names)
                        })

                        # 每對起終點最多保留 5 條路徑
                        if len([p for p in paths
                                if p["node_ids"][0] == src and p["node_ids"][-1] == sink]) >= 5:
                            break
                except nx.NetworkXNoPath:
                    continue
                except nx.NodeNotFound:
                    continue

        return paths

    # ====================================================================
    # 多維度風險評估
    # ====================================================================

    def _assess_structural_risk(self, path: Dict) -> Tuple[float, List[str]]:
        """
        結構風險評估

        風險因子：
        - 路徑過長（≥ 8 個節點）
        - 高扇出節點（out_degree ≥ 5）
        - 路徑包含組合迴圈的節點
        - 路徑跨越多個模組邊界
        """
        score = 0.0
        reasons = []
        node_ids = path["node_ids"]
        length = path["length"]

        # 路徑長度風險
        if length >= 10:
            score += 0.3
            reasons.append(f"路徑過長（{length} 個節點），可能導致時序違規或難以驗證")
        elif length >= 7:
            score += 0.15
            reasons.append(f"路徑較長（{length} 個節點），建議檢查時序約束")

        # 高扇出風險
        for nid in node_ids:
            if self.graph.has_node(nid):
                out_deg = self.graph.out_degree(nid)
                if out_deg >= 8:
                    score += 0.2
                    nd = self.graph.nodes[nid]
                    name = nd.get("label", nd.get("original_id", nid))
                    reasons.append(f"節點 {name} 扇出過高（{out_deg}），可能影響驅動能力或時序")
                    break
                elif out_deg >= 5:
                    score += 0.1
                    nd = self.graph.nodes[nid]
                    name = nd.get("label", nd.get("original_id", nid))
                    reasons.append(f"節點 {name} 扇出較高（{out_deg}）")
                    break

        # 跨模組風險
        module_count = len(path.get("modules", []))
        if module_count >= 3:
            score += 0.15
            reasons.append(f"路徑跨越 {module_count} 個模組，介面複雜度高")

        # 組合邏輯迴圈檢測
        comb_subgraph_nodes = [nid for nid in node_ids
                               if self.graph.has_node(nid)
                               and self.graph.nodes[nid].get("type", self.graph.nodes[nid].get("node_type", "")) != "reg"]
        if len(comb_subgraph_nodes) >= 2:
            sub = self.graph.subgraph(comb_subgraph_nodes)
            try:
                cycles = list(nx.simple_cycles(sub))
                if cycles:
                    score += 0.4
                    reasons.append("路徑中存在組合邏輯迴圈，可能導致電路不穩定")
            except Exception:
                pass

        return min(score, 1.0), reasons

    def _assess_assignment_risk(self, path: Dict) -> Tuple[float, List[str]]:
        """
        賦值風險評估

        風險因子：
        - 時序邏輯使用 blocking 賦值（應使用 non-blocking <=）
        - 組合邏輯使用 non-blocking 賦值（應使用 blocking =）
        """
        score = 0.0
        reasons = []

        for edata in path.get("edges", []):
            logic_type = edata.get("logic_type", "")
            assign_type = edata.get("assign_type", "")

            if logic_type == "sequential" and assign_type == "blocking":
                score += 0.25
                reasons.append("時序邏輯路徑使用了 blocking 賦值（=），應使用 non-blocking（<=）")
            elif logic_type == "combinational" and assign_type == "non-blocking":
                score += 0.2
                reasons.append("組合邏輯路徑使用了 non-blocking 賦值（<=），應使用 blocking（=）")

        return min(score, 1.0), reasons

    def _assess_width_risk(self, path: Dict) -> Tuple[float, List[str]]:
        """
        位元寬度風險評估

        風險因子：
        - 路徑中存在寬度不匹配的連線
        """
        score = 0.0
        reasons = []
        node_ids = path["node_ids"]

        for i in range(len(node_ids) - 1):
            src, tgt = node_ids[i], node_ids[i + 1]
            if not self.graph.has_node(src) or not self.graph.has_node(tgt):
                continue
            src_w = self.graph.nodes[src].get("width", 1)
            tgt_w = self.graph.nodes[tgt].get("width", 1)
            if src_w != tgt_w:
                src_name = self.graph.nodes[src].get("label", self.graph.nodes[src].get("original_id", src))
                tgt_name = self.graph.nodes[tgt].get("label", self.graph.nodes[tgt].get("original_id", tgt))
                score += 0.2
                reasons.append(
                    f"位元寬度不匹配：{src_name}（{src_w} bit）→ {tgt_name}（{tgt_w} bit），可能造成資料截斷或擴展錯誤"
                )

        return min(score, 1.0), reasons

    def _assess_semantic_risk(self, path: Dict, functional_description: str) -> Tuple[float, List[str]]:
        """
        語義風險評估（使用 AI 語義模型）

        將路徑描述與使用者提供的功能描述進行語義比對，
        若路徑行為與預期功能不符，標記較高風險。
        """
        score = 0.0
        reasons = []

        model = _get_sentence_model()
        if model is None or not functional_description.strip():
            return score, reasons

        # 建構路徑的語義描述
        path_desc_parts = []
        path_nodes = path["node_ids"]

        for nid in path_nodes:
            if not self.graph.has_node(nid):
                continue
            nd = self.graph.nodes[nid]
            ntype = nd.get("type", nd.get("node_type", ""))
            name = nd.get("label", nd.get("original_id", nid))
            width = nd.get("width", 1)
            path_desc_parts.append(f"{ntype} signal '{name}' ({width}-bit)")

        for edata in path.get("edges", []):
            logic = edata.get("logic_type", "")
            assign = edata.get("assign_type", "")
            if logic:
                path_desc_parts.append(f"{logic} {assign} assignment")

        path_description = "Circuit path: " + " → ".join(path_desc_parts)

        try:
            embeddings = model.encode([functional_description, path_description])
            similarity = cosine_similarity(embeddings[0].tolist(), embeddings[1].tolist())

            # 相似度越低 → 語義風險越高
            if similarity < 0.15:
                score = 0.35
                reasons.append(
                    f"此路徑與功能描述的語義相關度極低（{similarity:.2f}），電路行為可能與預期不符"
                )
            elif similarity < 0.30:
                score = 0.2
                reasons.append(
                    f"此路徑與功能描述的語義相關度偏低（{similarity:.2f}），建議確認邏輯正確性"
                )
        except Exception:
            pass

        return min(score, 1.0), reasons

    # ====================================================================
    # 主分析函式
    # ====================================================================

    def analyze(self, functional_description: str = "") -> List[Dict[str, Any]]:
        """
        執行完整的 AI 風險預測分析

        Args:
            functional_description: 使用者提供的電路功能描述

        Returns:
            風險分析結果列表（由高至低排序），每項包含：
            - path_id: 路徑唯一 ID
            - path_str: 路徑的可讀描述（A → B → C）
            - node_ids: 路徑節點 ID 列表
            - risk_score: 綜合風險分數（0.0 ~ 1.0）
            - risk_level: 風險等級（high / medium / low）
            - reasons: 風險原因列表
            - modules: 涉及的模組
        """
        if self.graph is None:
            return []

        paths = self.extract_logic_paths()
        if not paths:
            return []

        results = []

        for idx, path in enumerate(paths):
            # 多維度風險評估
            struct_score, struct_reasons = self._assess_structural_risk(path)
            assign_score, assign_reasons = self._assess_assignment_risk(path)
            width_score, width_reasons = self._assess_width_risk(path)
            semantic_score, semantic_reasons = self._assess_semantic_risk(path, functional_description)

            # 綜合風險分數（加權平均）
            total_score = (
                struct_score * 0.30
                + assign_score * 0.25
                + width_score * 0.25
                + semantic_score * 0.20
            )
            total_score = min(total_score, 1.0)

            all_reasons = struct_reasons + assign_reasons + width_reasons + semantic_reasons

            # 風險等級判定
            if total_score >= 0.5:
                risk_level = "high"
            elif total_score >= 0.25:
                risk_level = "medium"
            else:
                risk_level = "low"

            results.append({
                "path_id": f"path_{idx}",
                "path_str": path["path_str"],
                "node_ids": path["node_ids"],
                "node_names": path.get("node_names", []),
                "risk_score": round(total_score, 4),
                "risk_level": risk_level,
                "reasons": all_reasons if all_reasons else ["未檢測到明顯風險"],
                "modules": path.get("modules", []),
                "length": path["length"],
                "detail_scores": {
                    "structural": round(struct_score, 4),
                    "assignment": round(assign_score, 4),
                    "width": round(width_score, 4),
                    "semantic": round(semantic_score, 4)
                }
            })

        # 按風險分數由高至低排序
        results.sort(key=lambda r: r["risk_score"], reverse=True)

        self.risk_results = results
        return results

    def get_summary(self) -> Dict[str, Any]:
        """產生風險分析摘要"""
        if not self.risk_results:
            return {"total_paths": 0, "high": 0, "medium": 0, "low": 0}

        high = sum(1 for r in self.risk_results if r["risk_level"] == "high")
        medium = sum(1 for r in self.risk_results if r["risk_level"] == "medium")
        low = sum(1 for r in self.risk_results if r["risk_level"] == "low")

        return {
            "total_paths": len(self.risk_results),
            "high": high,
            "medium": medium,
            "low": low,
            "max_risk_score": self.risk_results[0]["risk_score"] if self.risk_results else 0,
            "top_risks": self.risk_results[:5]
        }
