"""
Stage 4: FastAPI Backend API
提供圖數據的 REST API 接口，支援前端視覺化與互動查詢
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Dict, List, Optional, Any
import torch
import networkx as nx
import json
import logging
import sys
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 導入之前的模組
from src.stage2_graph import SoftwareGraph
from src.stage3_labeler import BugLabeler

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 創建 FastAPI 應用
app = FastAPI(
    title="OmniTrace API",
    description="Code dependency graph analysis and risk visualization API",
    version="1.0.0"
)

# 配置 CORS（允許前端跨域請求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生產環境應限制為特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局數據緩存
_graph_cache = {
    "networkx_graph": None,
    "pyg_data": None,
    "labels_report": None,
    "graph_path": None
}


class GraphDataConverter:
    """將 NetworkX 圖與 PyG 數據轉換為前端格式"""
    
    def __init__(self, nx_graph: nx.DiGraph, pyg_data: Any, labels_report: Optional[Dict] = None):
        self.nx_graph = nx_graph
        self.pyg_data = pyg_data
        self.labels_report = labels_report or {}
        
    def convert_to_react_force_graph(self) -> Dict:
        """
        轉換為 react-force-graph 格式
        
        Returns:
            {
                "nodes": [...],
                "links": [...],
                "stats": {...}
            }
        """
        nodes = self._convert_nodes()
        links = self._convert_links()
        stats = self._compute_stats(nodes, links)
        
        logger.info(f"[INFO] 已轉換 {len(nodes)} 個節點與 {len(links)} 條邊")
        
        return {
            "nodes": nodes,
            "links": links,
            "stats": stats
        }
    
    def _convert_nodes(self) -> List[Dict]:
        """轉換節點數據"""
        nodes = []
        node_ids = self.pyg_data.node_ids if hasattr(self.pyg_data, 'node_ids') else []
        node_names = self.pyg_data.node_names if hasattr(self.pyg_data, 'node_names') else {}
        
        # 獲取標籤數據
        labels = self.pyg_data.y if hasattr(self.pyg_data, 'y') else None
        
        # 獲取特徵數據（用於詳細信息）
        features = self.pyg_data.x if hasattr(self.pyg_data, 'x') else None
        feature_names = self.pyg_data.feature_names if hasattr(self.pyg_data, 'feature_names') else []
        
        # 計算度數
        in_degrees = dict(self.nx_graph.in_degree())
        out_degrees = dict(self.nx_graph.out_degree())
        
        for idx, node_id in enumerate(node_ids):
            node_data = self.nx_graph.nodes.get(node_id, {})
            
            # 基本信息
            node_name = node_names.get(node_id, node_id)
            node_type = node_data.get('type', 'Unknown')
            
            # 風險分數（0-1）
            risk_score = 0.0
            risk_label = 0
            if labels is not None and idx < len(labels):
                risk_label = int(labels[idx].item())
                # 標籤 1 = 高風險 0.85；標籤 0 = 安全 0.1
                risk_score = 0.85 if risk_label == 1 else 0.1

            # 代碼行數
            loc = node_data.get('line_count', 0)

            # 圈複雜度
            complexity = node_data.get('cyclomatic_complexity', 0)

            # val：節點大小，依入度計算，最小為 5
            in_deg = in_degrees.get(node_id, 0)
            val = max(5, in_deg * 2)

            # color：依風險分數預先計算顏色字串，確保 risk_score=0.0 時也有顏色
            if risk_score >= 0.7:
                color = '#f85149'   # 高風險 — 紅色
            elif risk_score >= 0.4:
                color = '#f0e130'   # 中風險 — 黃色
            else:
                color = '#2ea043'   # 安全 — 綠色

            # 構建節點物件（符合 react-force-graph 預期欄位）
            node_obj = {
                "id": node_id,
                "name": node_name,
                "type": node_type,
                "val": val,
                "color": color,
                "risk_score": risk_score,
                "risk_label": risk_label,
                "loc": loc,
                "complexity": complexity,
                "in_degree": in_deg,
                "out_degree": out_degrees.get(node_id, 0),
            }
            
            # 添加特徵詳情（用於側邊欄）
            if features is not None and idx < len(features):
                feature_vector = features[idx].tolist()
                node_obj["features"] = {
                    feature_names[i]: float(feature_vector[i]) 
                    for i in range(min(len(feature_names), len(feature_vector)))
                }
            
            # 添加風險原因（來自 labels_report）
            risk_reasons = []
            risky_nodes = self.labels_report.get('risky_nodes', {})
            if node_id in risky_nodes:
                risk_reasons = risky_nodes[node_id].get('rules_matched', [])
            node_obj["risk_reasons"] = risk_reasons
            
            nodes.append(node_obj)
        
        return nodes
    
    def _convert_links(self) -> List[Dict]:
        """轉換邊數據"""
        links = []
        
        for source, target, edge_data in self.nx_graph.edges(data=True):
            dependency_type = edge_data.get('dependency_type', 'call')
            
            link_obj = {
                "source": source,
                "target": target,
                "dependency": dependency_type,
                # 根據依賴類型設置線條樣式
                "style": "solid" if dependency_type == "call" else "dashed"
            }
            
            links.append(link_obj)
        
        return links
    
    def _compute_stats(self, nodes: List[Dict], links: List[Dict]) -> Dict:
        """計算統計信息"""
        total_nodes = len(nodes)
        total_links = len(links)
        
        # 風險節點統計
        risky_nodes = [n for n in nodes if n['risk_label'] == 1]
        risk_count = len(risky_nodes)
        risk_percentage = (risk_count / total_nodes * 100) if total_nodes > 0 else 0
        
        # LOC 統計
        total_loc = sum(n['loc'] for n in nodes)
        avg_loc = total_loc / total_nodes if total_nodes > 0 else 0
        
        # 複雜度統計
        avg_complexity = sum(n['complexity'] for n in nodes) / total_nodes if total_nodes > 0 else 0
        
        # 孤立節點（無連接的節點）
        connected_nodes = set()
        for link in links:
            connected_nodes.add(link['source'])
            connected_nodes.add(link['target'])
        isolated_count = sum(1 for n in nodes if n['id'] not in connected_nodes)
        
        return {
            "total_nodes": total_nodes,
            "total_links": total_links,
            "risky_nodes": risk_count,
            "risk_percentage": round(risk_percentage, 2),
            "isolated_nodes": isolated_count,
            "total_loc": total_loc,
            "avg_loc": round(avg_loc, 2),
            "avg_complexity": round(avg_complexity, 2),
        }


def load_graph_data(graph_path: str = "output/graph_data.pt") -> Dict:
    """
    載入圖數據並緩存
    
    Args:
        graph_path: PyG 數據文件路徑
        
    Returns:
        包含 NetworkX 圖和 PyG 數據的字典
    """
    global _graph_cache
    
    # 檢查緩存
    if _graph_cache["graph_path"] == graph_path and _graph_cache["networkx_graph"] is not None:
        logger.info("[INFO] 使用已緩存的圖資料")
        return _graph_cache
    
    graph_file = Path(graph_path)
    if not graph_file.exists():
        raise FileNotFoundError(f"Graph data file not found: {graph_path}")
    
    logger.info(f"[INFO] 正在從 {graph_path} 載入圖資料")
    
    # 載入 PyG 數據
    pyg_data = torch.load(graph_path, weights_only=False)
    
    # 重建 NetworkX 圖（從 edge_index）
    nx_graph = nx.DiGraph()
    
    # 添加節點
    node_ids = pyg_data.node_ids if hasattr(pyg_data, 'node_ids') else []
    node_names = pyg_data.node_names if hasattr(pyg_data, 'node_names') else {}
    
    for node_id in node_ids:
        node_attrs = {
            'name': node_names.get(node_id, node_id),
            'type': 'Function',  # 默認類型
        }
        # 如果有額外屬性，從 pyg_data 中提取
        if hasattr(pyg_data, 'node_attributes'):
            node_attrs.update(pyg_data.node_attributes.get(node_id, {}))
        
        nx_graph.add_node(node_id, **node_attrs)
    
    # 添加邊
    edge_index = pyg_data.edge_index
    edge_attrs = pyg_data.edge_attr if hasattr(pyg_data, 'edge_attr') else None
    
    for i in range(edge_index.shape[1]):
        source_idx = int(edge_index[0, i].item())
        target_idx = int(edge_index[1, i].item())
        
        source_id = node_ids[source_idx]
        target_id = node_ids[target_idx]
        
        edge_data = {'dependency_type': 'call'}
        if edge_attrs is not None and i < len(edge_attrs):
            edge_data['weight'] = float(edge_attrs[i].item())
        
        nx_graph.add_edge(source_id, target_id, **edge_data)
    
    # 載入 labels_report（如果存在）
    labels_report = None
    report_path = Path("output/labels_report.json")
    if report_path.exists():
        with open(report_path, 'r', encoding='utf-8') as f:
            labels_report = json.load(f)
    
    # 更新緩存
    _graph_cache = {
        "networkx_graph": nx_graph,
        "pyg_data": pyg_data,
        "labels_report": labels_report,
        "graph_path": graph_path
    }
    
    logger.info(f"[INFO] 已載入 {len(node_ids)} 個節點與 {edge_index.shape[1]} 條邊")
    
    return _graph_cache


@app.get("/")
async def root():
    """API 根路徑"""
    return {
        "name": "OmniTrace API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "/api/graph",
            "/api/graph/stats",
            "/api/nodes/{node_id}",
            "/docs"
        ]
    }


@app.get("/api/graph")
async def get_graph(
    graph_path: str = "output/graph_data.pt",
    min_risk: Optional[float] = None,
    node_type: Optional[str] = None
):
    """
    獲取完整圖數據（react-force-graph 格式）
    
    Query Parameters:
        graph_path: 數據文件路徑（默認 output/graph_data.pt）
        min_risk: 最小風險分數過濾（0-1）
        node_type: 節點類型過濾（Function/Class/Struct）
        
    Returns:
        {
            "nodes": [...],
            "links": [...],
            "stats": {...}
        }
    """
    try:
        # 載入數據
        cache = load_graph_data(graph_path)
        
        # 轉換為前端格式
        converter = GraphDataConverter(
            cache["networkx_graph"],
            cache["pyg_data"],
            cache["labels_report"]
        )
        graph_data = converter.convert_to_react_force_graph()
        
        # 應用過濾
        if min_risk is not None:
            graph_data["nodes"] = [
                n for n in graph_data["nodes"] 
                if n["risk_score"] >= min_risk
            ]
            # 重新計算連接
            node_ids = {n["id"] for n in graph_data["nodes"]}
            graph_data["links"] = [
                l for l in graph_data["links"] 
                if l["source"] in node_ids and l["target"] in node_ids
            ]
        
        if node_type is not None:
            graph_data["nodes"] = [
                n for n in graph_data["nodes"] 
                if n["type"] == node_type
            ]
            # 重新計算連接
            node_ids = {n["id"] for n in graph_data["nodes"]}
            graph_data["links"] = [
                l for l in graph_data["links"] 
                if l["source"] in node_ids and l["target"] in node_ids
            ]
        
        return JSONResponse(content=graph_data)
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error loading graph: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/graph/stats")
async def get_graph_stats(graph_path: str = "output/graph_data.pt"):
    """
    獲取圖統計信息
    
    Returns:
        統計數據（節點數、邊數、風險節點等）
    """
    try:
        cache = load_graph_data(graph_path)
        converter = GraphDataConverter(
            cache["networkx_graph"],
            cache["pyg_data"],
            cache["labels_report"]
        )
        graph_data = converter.convert_to_react_force_graph()
        
        return JSONResponse(content=graph_data["stats"])
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/nodes/{node_id}")
async def get_node_details(node_id: str, graph_path: str = "output/graph_data.pt"):
    """
    獲取單個節點的詳細信息
    
    Args:
        node_id: 節點 ID
        
    Returns:
        節點詳細數據，包括特徵向量、風險原因、鄰居節點等
    """
    try:
        cache = load_graph_data(graph_path)
        converter = GraphDataConverter(
            cache["networkx_graph"],
            cache["pyg_data"],
            cache["labels_report"]
        )
        graph_data = converter.convert_to_react_force_graph()
        
        # 查找節點
        node = next((n for n in graph_data["nodes"] if n["id"] == node_id), None)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
        
        # 添加鄰居信息
        neighbors_out = []
        neighbors_in = []
        for link in graph_data["links"]:
            if link["source"] == node_id:
                target_node = next((n for n in graph_data["nodes"] if n["id"] == link["target"]), None)
                if target_node:
                    neighbors_out.append({
                        "id": target_node["id"],
                        "name": target_node["name"],
                        "dependency": link["dependency"]
                    })
            elif link["target"] == node_id:
                source_node = next((n for n in graph_data["nodes"] if n["id"] == link["source"]), None)
                if source_node:
                    neighbors_in.append({
                        "id": source_node["id"],
                        "name": source_node["name"],
                        "dependency": link["dependency"]
                    })
        
        node["neighbors_out"] = neighbors_out
        node["neighbors_in"] = neighbors_in
        
        return JSONResponse(content=node)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting node details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/reload")
async def reload_graph_data(graph_path: str = "output/graph_data.pt"):
    """
    重新載入圖數據（清除緩存）
    
    Returns:
        重新載入後的統計信息
    """
    global _graph_cache
    _graph_cache = {
        "networkx_graph": None,
        "pyg_data": None,
        "labels_report": None,
        "graph_path": None
    }
    
    logger.info("Cache cleared, reloading data...")
    
    try:
        cache = load_graph_data(graph_path)
        converter = GraphDataConverter(
            cache["networkx_graph"],
            cache["pyg_data"],
            cache["labels_report"]
        )
        graph_data = converter.convert_to_react_force_graph()
        
        return JSONResponse(content={
            "status": "success",
            "message": "Graph data reloaded",
            "stats": graph_data["stats"]
        })
        
    except Exception as e:
        logger.error(f"Error reloading graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 啟動說明
if __name__ == "__main__":
    import uvicorn
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║              OmniTrace API Server                         ║
    ╚═══════════════════════════════════════════════════════════╝
    
    Server starting on: http://localhost:8000
    API Documentation:  http://localhost:8000/docs
    
    Main Endpoints:
      GET  /api/graph          - Get full graph data
      GET  /api/graph/stats    - Get statistics
      GET  /api/nodes/{id}     - Get node details
      POST /api/graph/reload   - Reload graph data
    
    Press Ctrl+C to stop the server.
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
