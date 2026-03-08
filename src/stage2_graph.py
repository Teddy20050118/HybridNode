"""
階段 2：通用圖形 IR 與 NetworkX 整合
功能：將解析結果轉換為圖形結構，並進行靜態分析
"""

import json
import networkx as nx
from typing import Dict, List, Set, Tuple, Optional, Any
from collections import defaultdict
import numpy as np
from pathlib import Path


class SoftwareGraph:
    """軟體依賴圖分析器（基於 NetworkX）"""
    
    def __init__(self):
        """初始化圖形結構"""
        self.graph = nx.DiGraph()  # 有向圖
        self.nodes_data: Dict[str, Dict] = {}
        self.edges_data: List[Dict] = []
        
        # 分析結果緩存
        self._god_objects: Optional[List[Tuple[str, float]]] = None
        self._cycles: Optional[List[List[str]]] = None
        self._coupling_matrix: Optional[Dict] = None
    
    def load_from_json(self, json_path: str):
        """
        從 JSON 文件加載解析結果
        支援兩種格式：
        1. 單一字典：{"nodes": [...], "edges": [...]}
        2. 多文件列表：[{"file": "a.cpp", "nodes": [...], "edges": [...]}, ...]
        
        Args:
            json_path: JSON 文件路徑
        """
        import os
        
        # 安全檢查：確保傳入的是檔案而不是目錄
        if os.path.isdir(json_path):
            raise ValueError(f"[ERROR] 預期是 JSON 檔案，但收到的是資料夾路徑: {json_path}")
        
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"[ERROR] JSON 檔案不存在: {json_path}")
        
        print(f"[INFO] 加載數據：{json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 數據扁平化：判斷是單一字典還是多文件列表
        if isinstance(data, list):
            # 多文件格式：需要合併所有 nodes 和 edges
            print(f"[INFO] 檢測到多文件格式（{len(data)} 個文件），正在扁平化數據...")
            all_nodes = []
            all_edges = []
            
            for file_data in data:
                file_name = file_data.get('file', 'unknown')
                nodes = file_data.get('nodes', [])
                edges = file_data.get('edges', [])
                
                if nodes:
                    all_nodes.extend(nodes)
                if edges:
                    all_edges.extend(edges)
                
                print(f"[INFO]   - {file_name}: {len(nodes)} 節點, {len(edges)} 邊")
            
            print(f"[INFO] 扁平化完成：總共 {len(all_nodes)} 節點, {len(all_edges)} 邊")
            self.build_graph(all_nodes, all_edges)
            
        elif isinstance(data, dict):
            # 單一字典格式：直接使用
            print(f"[INFO] 檢測到單一字典格式")
            nodes = data.get('nodes', [])
            edges = data.get('edges', [])
            self.build_graph(nodes, edges)
        else:
            raise ValueError(f"[ERROR] 不支援的數據格式: {type(data).__name__}，預期 list 或 dict")
        
        print(f"[SUCCESS] 圖形構建完成：{self.graph.number_of_nodes()} 節點, {self.graph.number_of_edges()} 邊")
    
    def load_from_dict(self, data: Dict):
        """
        從字典加載解析結果
        
        Args:
            data: 包含 nodes 和 edges 的字典
        """
        self.build_graph(data['nodes'], data['edges'])
    
    def build_graph(self, nodes: List[Dict], edges: List[Dict]):
        """
        構建 NetworkX 圖形
        
        Args:
            nodes: 節點列表
            edges: 邊列表
        """
        # 容錯處理：確保 nodes 和 edges 不為 None
        if nodes is None:
            nodes = []
            print(f"[WARN] nodes 為 None，已初始化為空列表")
        if edges is None:
            edges = []
            print(f"[WARN] edges 為 None，已初始化為空列表")
        
        # 添加節點
        for node in nodes:
            node_id = node.get('name') or node.get('id')
            if not node_id:
                print(f"[WARN] 跳過無效節點（缺少 name 和 id）: {node}")
                continue
            self.graph.add_node(node_id, **node)
            self.nodes_data[node_id] = node
        
        # 添加邊
        for edge in edges:
            source = edge.get('from')
            target = edge.get('to')
            
            if source and target and source in self.graph and target in self.graph:
                self.graph.add_edge(source, target, **edge)
                self.edges_data.append(edge)
            else:
                # 處理跨文件引用的情況
                if source and target:
                    # 確保節點存在
                    if source not in self.graph:
                        self.graph.add_node(source, type='ExternalReference', name=source)
                    if target not in self.graph:
                        self.graph.add_node(target, type='ExternalReference', name=target)
                    
                    self.graph.add_edge(source, target, **edge)
                    self.edges_data.append(edge)
    
    # ========== 靜態分析：God Object 偵測 ==========
    
    def detect_god_objects(self, threshold: float = 0.15) -> List[Tuple[str, Dict[str, float]]]:
        """
        偵測 God Object（上帝對象）
        使用多個指標綜合判斷：
        1. Degree Centrality（度中心性）
        2. PageRank（權威性）
        3. Betweenness Centrality（介數中心性）
        
        Args:
            threshold: 閾值（超過此值視為 God Object）
            
        Returns:
            [(節點名稱, {指標字典}), ...]
        """
        print(f"[INFO] 正在檢測 God Object...")
        
        # 計算各項指標
        degree_centrality = nx.degree_centrality(self.graph)
        pagerank = nx.pagerank(self.graph, alpha=0.85)
        
        # 對於大型圖，介數中心性計算較慢，這裡使用近似算法
        try:
            betweenness = nx.betweenness_centrality(self.graph, k=min(100, self.graph.number_of_nodes()))
        except:
            betweenness = {node: 0 for node in self.graph.nodes()}
        
        # 綜合評分
        god_candidates = []
        for node in self.graph.nodes():
            # 只分析類別和函數
            node_data = self.graph.nodes[node]
            if node_data.get('type') not in ('CXXRecordDecl', 'FunctionDecl'):
                continue
            
            metrics = {
                'degree_centrality': degree_centrality.get(node, 0),
                'pagerank': pagerank.get(node, 0),
                'betweenness_centrality': betweenness.get(node, 0),
                'in_degree': self.graph.in_degree(node),
                'out_degree': self.graph.out_degree(node)
            }
            
            # 綜合評分（加權平均）
            composite_score = (
                metrics['degree_centrality'] * 0.3 +
                metrics['pagerank'] * 0.4 +
                metrics['betweenness_centrality'] * 0.3
            )
            
            metrics['composite_score'] = composite_score
            
            if composite_score > threshold:
                god_candidates.append((node, metrics))
        
        # 按綜合評分排序
        god_candidates.sort(key=lambda x: x[1]['composite_score'], reverse=True)
        self._god_objects = god_candidates
        
        print(f"   發現 {len(god_candidates)} 個潛在 God Object")
        for node, metrics in god_candidates[:5]:
            print(f"   - {node}: 評分 {metrics['composite_score']:.3f}")
        
        return god_candidates
    
    # ========== 靜態分析：循環依賴偵測 ==========
    
    def detect_circular_dependencies(self) -> List[List[str]]:
        """
        偵測循環依賴（強連通分量）
        
        Returns:
            循環依賴的節點組列表
        """
        print("\n正在檢測循環依賴...")
        
        # 使用 Tarjan 算法找出所有強連通分量
        sccs = list(nx.strongly_connected_components(self.graph))
        
        # 過濾掉單節點的 SCC（自己不算循環）
        cycles = [list(scc) for scc in sccs if len(scc) > 1]
        
        self._cycles = cycles
        
        if cycles:
            print(f"[WARN] 發現 {len(cycles)} 組循環依賴：")
            for i, cycle in enumerate(cycles[:5], 1):  # 顯示前 5 個
                print(f"[WARN]    {i}. {' ↔ '.join(cycle[:5])}" + (" ..." if len(cycle) > 5 else ""))
        else:
            print(f"[SUCCESS] 未發現循環依賴")
        
        return cycles
    
    def find_cycle_paths(self, cycle_nodes: Set[str], max_paths: int = 3) -> List[List[str]]:
        """
        找出循環依賴中的具體路徑
        
        Args:
            cycle_nodes: 循環中的節點集合
            max_paths: 最多返回幾條路徑
            
        Returns:
            路徑列表
        """
        subgraph = self.graph.subgraph(cycle_nodes)
        paths = []
        
        # 嘗試從每個節點出發找環
        for node in list(cycle_nodes)[:max_paths]:
            try:
                cycle = nx.find_cycle(subgraph, source=node)
                path = [edge[0] for edge in cycle] + [cycle[-1][1]]
                paths.append(path)
            except nx.NetworkXNoCycle:
                continue
        
        return paths
    
    # ========== 靜態分析：耦合度量化 ==========
    
    def calculate_coupling_metrics(self) -> Dict[str, Any]:
        """
        計算模組間的耦合度指標
        包括：
        1. Afferent Coupling (Ca): 傳入耦合（有多少模組依賴此模組）
        2. Efferent Coupling (Ce): 傳出耦合（此模組依賴多少其他模組）
        3. Instability (I): 不穩定性 = Ce / (Ca + Ce)
        4. Coupling Between Objects (CBO): 類別間耦合
        
        Returns:
            耦合度指標字典
        """
        print("\n正在計算耦合度...")
        
        coupling_data = {}
        
        for node in self.graph.nodes():
            node_data = self.graph.nodes[node]
            
            # Afferent Coupling: 有多少節點指向此節點
            ca = self.graph.in_degree(node)
            
            # Efferent Coupling: 此節點指向多少其他節點
            ce = self.graph.out_degree(node)
            
            # Instability: 穩定性指標 (0 = 最穩定, 1 = 最不穩定)
            instability = ce / (ca + ce) if (ca + ce) > 0 else 0
            
            # CBO: 與此節點有關聯的唯一節點數
            neighbors = set(self.graph.predecessors(node)) | set(self.graph.successors(node))
            cbo = len(neighbors)
            
            coupling_data[node] = {
                'afferent_coupling': ca,
                'efferent_coupling': ce,
                'instability': instability,
                'coupling_between_objects': cbo,
                'total_coupling': ca + ce
            }
        
        # 找出高耦合節點
        high_coupling = sorted(
            coupling_data.items(),
            key=lambda x: x[1]['total_coupling'],
            reverse=True
        )[:10]
        
        print(f"   前 10 個高耦合節點：")
        for node, metrics in high_coupling:
            print(f"   - {node}: Ca={metrics['afferent_coupling']}, "
                  f"Ce={metrics['efferent_coupling']}, "
                  f"I={metrics['instability']:.2f}")
        
        self._coupling_matrix = coupling_data
        return coupling_data
    
    def calculate_module_coupling_matrix(self, modules: Optional[Dict[str, List[str]]] = None) -> np.ndarray:
        """
        計算模組間的耦合矩陣
        
        Args:
            modules: 模組定義 {模組名: [節點列表]}
                    如果為 None，則按文件自動分組
        
        Returns:
            耦合矩陣 (NumPy array)
        """
        if modules is None:
            # 自動按文件分組
            modules = self._group_by_file()
        
        module_names = list(modules.keys())
        n = len(module_names)
        coupling_matrix = np.zeros((n, n))
        
        for i, mod1 in enumerate(module_names):
            for j, mod2 in enumerate(module_names):
                if i != j:
                    # 計算 mod1 -> mod2 的依賴數量
                    dependencies = 0
                    for node1 in modules[mod1]:
                        for node2 in modules[mod2]:
                            if self.graph.has_edge(node1, node2):
                                dependencies += 1
                    coupling_matrix[i][j] = dependencies
        
        return coupling_matrix
    
    def _group_by_file(self) -> Dict[str, List[str]]:
        """按源文件分組節點"""
        file_groups = defaultdict(list)
        
        for node, data in self.graph.nodes(data=True):
            location = data.get('location', {})
            file_path = location.get('file', 'unknown')
            
            if file_path and file_path != 'unknown':
                file_name = Path(file_path).name
                file_groups[file_name].append(node)
        
        return dict(file_groups)
    
    # ========== 其他實用功能 ==========
    
    def get_node_neighbors(self, node_name: str, depth: int = 1) -> Dict[str, Set[str]]:
        """
        獲取節點的鄰居（依賴關係）
        
        Args:
            node_name: 節點名稱
            depth: 搜索深度
            
        Returns:
            {
                'predecessors': 前驅節點集合,
                'successors': 後繼節點集合
            }
        """
        if node_name not in self.graph:
            raise ValueError(f"節點 {node_name} 不存在")
        
        predecessors = set()
        successors = set()
        
        # BFS 搜索
        for d in range(1, depth + 1):
            if d == 1:
                predecessors.update(self.graph.predecessors(node_name))
                successors.update(self.graph.successors(node_name))
            else:
                new_pred = set()
                new_succ = set()
                for p in list(predecessors):
                    new_pred.update(self.graph.predecessors(p))
                for s in list(successors):
                    new_succ.update(self.graph.successors(s))
                predecessors.update(new_pred)
                successors.update(new_succ)
        
        return {
            'predecessors': predecessors,
            'successors': successors
        }
    
    def calculate_graph_metrics(self) -> Dict[str, Any]:
        """計算整體圖形指標"""
        metrics = {
            'num_nodes': self.graph.number_of_nodes(),
            'num_edges': self.graph.number_of_edges(),
            'density': nx.density(self.graph),
            'is_dag': nx.is_directed_acyclic_graph(self.graph)
        }
        
        # 計算平均度
        degrees = [d for n, d in self.graph.degree()]
        metrics['avg_degree'] = np.mean(degrees) if degrees else 0
        metrics['max_degree'] = max(degrees) if degrees else 0
        
        # 連通分量
        try:
            metrics['num_weakly_connected_components'] = nx.number_weakly_connected_components(self.graph)
            metrics['num_strongly_connected_components'] = nx.number_strongly_connected_components(self.graph)
        except:
            pass
        
        return metrics
    
    # ========== 導出功能 ==========
    
    def export_for_visualization(self, output_path: str):
        """
        導出為前端可視化格式（react-force-graph）
        
        Args:
            output_path: 輸出文件路徑
        """
        vis_data = {
            'nodes': [],
            'links': []
        }
        
        # 轉換節點
        for node, data in self.graph.nodes(data=True):
            vis_node = {
                'id': node,
                'name': node,
                'type': data.get('type', 'unknown'),
                'group': self._get_node_group(data),
                # 添加額外屬性用於視覺化
                'size': self.graph.degree(node),
                'complexity': data.get('cyclomatic_complexity', 1)
            }
            vis_data['nodes'].append(vis_node)
        
        # 轉換邊
        for source, target, data in self.graph.edges(data=True):
            vis_link = {
                'source': source,
                'target': target,
                'type': data.get('type', 'unknown')
            }
            vis_data['links'].append(vis_link)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(vis_data, f, indent=2, ensure_ascii=False)
        
        print(f"[SUCCESS] 視覺化數據已保存至：{output_path}")
    
    def _get_node_group(self, node_data: Dict) -> str:
        """根據節點類型返回分組標識"""
        node_type = node_data.get('type', 'unknown')
        type_mapping = {
            'FunctionDecl': 'function',
            'CXXRecordDecl': 'class',
            'VarDecl': 'variable',
            'ExternalReference': 'external'
        }
        return type_mapping.get(node_type, 'other')
    
    def export_analysis_report(self, output_path: str):
        """
        導出完整的分析報告
        
        Args:
            output_path: 輸出文件路徑
        """
        report = {
            'graph_metrics': self.calculate_graph_metrics(),
            'god_objects': [
                {'name': name, 'metrics': metrics}
                for name, metrics in (self._god_objects or self.detect_god_objects())
            ],
            'circular_dependencies': [
                {'nodes': cycle, 'size': len(cycle)}
                for cycle in (self._cycles or self.detect_circular_dependencies())
            ],
            'coupling_metrics': self._coupling_matrix or self.calculate_coupling_metrics()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"[SUCCESS] 分析報告已保存至：{output_path}")
    
    def print_summary(self):
        """打印分析摘要"""
        print("\n" + "="*60)
        print("軟體圖形分析摘要")
        print("="*60)
        
        metrics = self.calculate_graph_metrics()
        print(f"節點總數: {metrics['num_nodes']}")
        print(f"邊總數: {metrics['num_edges']}")
        print(f"圖密度: {metrics['density']:.4f}")
        print(f"平均度數: {metrics['avg_degree']:.2f}")
        print(f"是否為 DAG: {'是' if metrics['is_dag'] else '否'}")
        
        if self._god_objects:
            print(f"\nGod Objects: {len(self._god_objects)} 個")
        
        if self._cycles:
            print(f"循環依賴: {len(self._cycles)} 組")
        
        print("="*60)


def analyze_codebase(json_path: str, output_dir: str = "./output"):
    """
    完整的代碼庫分析流程
    
    Args:
        json_path: 階段1 輸出的 JSON 文件
        output_dir: 輸出目錄
    """
    # 創建輸出目錄
    Path(output_dir).mkdir(exist_ok=True)
    
    # 初始化圖形
    graph = SoftwareGraph()
    graph.load_from_json(json_path)
    
    # 執行各項分析
    graph.detect_god_objects()
    graph.detect_circular_dependencies()
    graph.calculate_coupling_metrics()
    
    # 導出結果
    graph.export_for_visualization(f"{output_dir}/visualization.json")
    graph.export_analysis_report(f"{output_dir}/analysis_report.json")
    
    # 打印摘要
    graph.print_summary()
    
    return graph


if __name__ == "__main__":
    print("階段 2 圖形分析模組已就緒！")
    
    # 使用示例：
    # graph = analyze_codebase("output.json", "./analysis_output")
