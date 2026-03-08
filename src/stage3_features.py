"""
階段 3：AI 特徵工程 (Feature Engineering)
功能：將 NetworkX 圖形轉換為 PyTorch Geometric 可訓練的張量格式
"""

import numpy as np
import networkx as nx
import torch
from torch_geometric.data import Data
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from typing import Dict, List, Tuple, Optional, Any
import warnings

warnings.filterwarnings('ignore')


class FeatureExtractor:
    """
    特徵提取器：將 NetworkX 圖形節點轉換為多維特徵向量
    
    特徵組成：
    1. 數值特徵 (Numerical)：lines_of_code, cyclomatic_complexity, parameter_count
    2. 類別特徵 (Categorical)：節點類型的 One-hot Encoding
    3. 語義特徵 (Semantic)：函數/類別名稱的文本嵌入
    4. 結構特徵 (Structural)：In-degree, Out-degree
    """
    
    # 節點類型映射（用於 One-hot Encoding）
    NODE_TYPES = ['FunctionDecl', 'CXXRecordDecl', 'VarDecl', 'ExternalReference', 'Other']
    
    def __init__(self, 
                 embedding_model: str = 'all-MiniLM-L6-v2',
                 scaler_type: str = 'standard',
                 use_cache: bool = True):
        """
        初始化特徵提取器
        
        Args:
            embedding_model: Sentence Transformer 模型名稱
            scaler_type: 數值特徵縮放方式 ('standard' 或 'minmax')
            use_cache: 是否快取語義嵌入結果
        """
        print(f"[INFO] 初始化特徵提取器...")
        print(f"[INFO]    加載語義嵌入模型: {embedding_model}")
        
        # 載入預訓練的語義嵌入模型
        self.embedding_model = SentenceTransformer(embedding_model)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        
        # 選擇數值特徵縮放器
        if scaler_type == 'standard':
            self.scaler = StandardScaler()
        elif scaler_type == 'minmax':
            self.scaler = MinMaxScaler()
        else:
            raise ValueError(f"不支援的縮放類型: {scaler_type}")
        
        self.use_cache = use_cache
        self.embedding_cache: Dict[str, np.ndarray] = {}
        
        # 特徵維度記錄
        self.num_numerical_features = 5  # lines_of_code, complexity, param_count, in_degree, out_degree
        self.num_categorical_features = len(self.NODE_TYPES)
        self.num_semantic_features = self.embedding_dim
        self.total_feature_dim = (
            self.num_numerical_features + 
            self.num_categorical_features + 
            self.num_semantic_features
        )
        
        print(f"[INFO]    語義嵌入維度: {self.embedding_dim}")
        print(f"[INFO]    總特徵維度: {self.total_feature_dim}")
        print(f"[INFO]      - 數值特徵: {self.num_numerical_features}")
        print(f"[INFO]      - 類別特徵: {self.num_categorical_features}")
        print(f"[INFO]      - 語義特徵: {self.num_semantic_features}")
    
    def extract_numerical_features(self, node_data: Dict) -> np.ndarray:
        """
        提取數值特徵
        
        Args:
            node_data: 節點數據字典
            
        Returns:
            數值特徵向量 (shape: [3])
        """
        # 提取原始數值
        lines_of_code = float(node_data.get('line_count', 0))
        complexity = float(node_data.get('cyclomatic_complexity', 1))
        
        # 計算參數數量
        parameters = node_data.get('parameters', [])
        param_count = float(len(parameters)) if isinstance(parameters, list) else 0.0
        
        return np.array([lines_of_code, complexity, param_count], dtype=np.float32)
    
    def extract_categorical_features(self, node_data: Dict) -> np.ndarray:
        """
        提取類別特徵 (One-hot Encoding)
        
        Args:
            node_data: 節點數據字典
            
        Returns:
            One-hot 向量 (shape: [len(NODE_TYPES)])
        """
        node_type = node_data.get('type', 'Other')
        
        # 創建 One-hot 向量
        one_hot = np.zeros(len(self.NODE_TYPES), dtype=np.float32)
        
        try:
            idx = self.NODE_TYPES.index(node_type)
            one_hot[idx] = 1.0
        except ValueError:
            # 未知類型歸為 'Other'
            idx = self.NODE_TYPES.index('Other')
            one_hot[idx] = 1.0
        
        return one_hot
    
    def extract_semantic_features(self, node_data: Dict) -> np.ndarray:
        """
        提取語義特徵 (文本嵌入)
        
        Args:
            node_data: 節點數據字典
            
        Returns:
            語義嵌入向量 (shape: [embedding_dim])
        """
        # 獲取節點名稱
        name = node_data.get('name', node_data.get('id', 'unknown'))
        
        # 檢查快取
        if self.use_cache and name in self.embedding_cache:
            return self.embedding_cache[name]
        
        # 構建文本描述（包含類型和名稱）
        node_type = node_data.get('type', 'unknown')
        text = f"{node_type} {name}"
        
        # 生成嵌入
        embedding = self.embedding_model.encode(text, convert_to_numpy=True)
        embedding = embedding.astype(np.float32)
        
        # 快取結果
        if self.use_cache:
            self.embedding_cache[name] = embedding
        
        return embedding
    
    def extract_structural_features(self, graph: nx.DiGraph, node_id: str) -> np.ndarray:
        """
        提取結構特徵
        
        Args:
            graph: NetworkX 圖形
            node_id: 節點 ID
            
        Returns:
            結構特徵向量 (shape: [2])
        """
        in_degree = float(graph.in_degree(node_id))
        out_degree = float(graph.out_degree(node_id))
        
        return np.array([in_degree, out_degree], dtype=np.float32)
    
    def extract_node_features(self, graph: nx.DiGraph, node_id: str) -> np.ndarray:
        """
        提取單個節點的完整特徵向量
        
        Args:
            graph: NetworkX 圖形
            node_id: 節點 ID
            
        Returns:
            完整特徵向量 (shape: [total_feature_dim])
        """
        node_data = graph.nodes[node_id]
        
        # 1. 數值特徵
        numerical = self.extract_numerical_features(node_data)
        
        # 2. 結構特徵（度數）
        structural = self.extract_structural_features(graph, node_id)
        
        # 3. 合併數值特徵和結構特徵
        numerical_all = np.concatenate([numerical, structural])
        
        # 4. 類別特徵
        categorical = self.extract_categorical_features(node_data)
        
        # 5. 語義特徵
        semantic = self.extract_semantic_features(node_data)
        
        # 6. 拼接所有特徵
        feature_vector = np.concatenate([
            numerical_all,   # 5 維
            categorical,     # len(NODE_TYPES) 維
            semantic         # embedding_dim 維
        ])
        
        return feature_vector
    
    def build_feature_matrix(self, graph: nx.DiGraph) -> Tuple[np.ndarray, List[str]]:
        """
        為整個圖形構建特徵矩陣
        
        Args:
            graph: NetworkX 圖形
            
        Returns:
            特徵矩陣 (shape: [num_nodes, total_feature_dim])
            節點 ID 列表（用於索引映射）
        """
        print(f"\n[INFO] 正在提取圖形特徵...")
        print(f"[INFO]    節點總數: {graph.number_of_nodes()}")
        
        # 獲取所有節點 ID（排序以保證穩定性）
        node_ids = sorted(list(graph.nodes()))
        num_nodes = len(node_ids)
        
        # 初始化特徵矩陣
        feature_matrix = np.zeros((num_nodes, self.total_feature_dim), dtype=np.float32)
        
        # 逐個提取節點特徵
        for idx, node_id in enumerate(node_ids):
            feature_matrix[idx] = self.extract_node_features(graph, node_id)
            
            if (idx + 1) % 10 == 0 or idx == num_nodes - 1:
                print(f"[INFO]    已處理: {idx + 1}/{num_nodes} 節點")
        
        # 對數值特徵部分進行縮放（前5個特徵）
        print(f"\n[INFO] 正在縮放數值特徵...")
        numerical_features = feature_matrix[:, :self.num_numerical_features]
        
        # 處理全零列（避免縮放錯誤）
        non_zero_mask = np.any(numerical_features != 0, axis=1)
        if non_zero_mask.any():
            scaled_features = numerical_features.copy()
            scaled_features[non_zero_mask] = self.scaler.fit_transform(
                numerical_features[non_zero_mask]
            )
            feature_matrix[:, :self.num_numerical_features] = scaled_features
        
        print(f"[INFO]    特徵矩陣形狀: {feature_matrix.shape}")

        # [INFO] 空矩陣守衛：當圖形無節點時（如所有檔案解析失敗），
        # feature_matrix.shape = (0, D)，呼叫 .min()/.max() 會丟出
        # ValueError: zero-size array to reduction operation minimum
        # 此時直接提早回傳，避免程式崩潰。
        if feature_matrix.size == 0:
            print("[WARN]    特徵矩陣為空（圖形無有效節點），跳過縮放步驟")
            return feature_matrix, node_ids

        print(f"[INFO]    特徵範圍: [{feature_matrix.min():.4f}, {feature_matrix.max():.4f}]")

        return feature_matrix, node_ids



def to_pyg_data(graph: nx.DiGraph, 
                extractor: Optional[FeatureExtractor] = None,
                include_edge_attr: bool = False) -> Data:
    """
    將 NetworkX 圖形轉換為 PyTorch Geometric Data 物件
    
    Args:
        graph: NetworkX 有向圖
        extractor: 特徵提取器（如果為 None 則創建新的）
        include_edge_attr: 是否包含邊特徵
        
    Returns:
        PyTorch Geometric Data 物件
    """
    print("\n" + "="*60)
    print("[INFO] 開始轉換 NetworkX 圖形至 PyTorch Geometric 格式")
    print("="*60)
    
    # 創建或使用特徵提取器
    if extractor is None:
        extractor = FeatureExtractor()
    
    # 構建特徵矩陣
    feature_matrix, node_ids = extractor.build_feature_matrix(graph)

    # [INFO] 零節點雙重防禦：
    # bridge.py 的 run() 在 Stage 2 後已加了 0 節點早退，
    # 此處是最後一道防線，確保即使繞過前面的守衛，
    # to_pyg_data 也不會因空矩陣而崩潰。
    if len(node_ids) == 0:
        print("[WARN] to_pyg_data: 圖形節點數為 0，回傳空 Data 物件")
        empty_data = Data(
            x=torch.zeros((0, extractor.total_feature_dim), dtype=torch.float32),
            edge_index=torch.empty((2, 0), dtype=torch.long),
        )
        empty_data.num_nodes = 0
        empty_data.node_ids = []
        empty_data.node_to_idx = {}
        empty_data.num_numerical_features = extractor.num_numerical_features
        empty_data.num_categorical_features = extractor.num_categorical_features
        empty_data.num_semantic_features = extractor.num_semantic_features
        return empty_data

    # 創建節點 ID 到索引的映射
    node_to_idx = {node_id: idx for idx, node_id in enumerate(node_ids)}

    
    print(f"\n[INFO] 正在構建邊索引...")
    
    # 構建邊索引 (edge_index)
    edge_list = []
    edge_types = []
    
    for u, v, edge_data in graph.edges(data=True):
        if u in node_to_idx and v in node_to_idx:
            src_idx = node_to_idx[u]
            dst_idx = node_to_idx[v]
            edge_list.append([src_idx, dst_idx])
            
            if include_edge_attr:
                edge_type = edge_data.get('type', 'unknown')
                edge_types.append(edge_type)
    
    # 轉換為張量
    if len(edge_list) > 0:
        edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        print(f"[INFO]    邊索引形狀: {edge_index.shape}")
    else:
        # 處理無邊圖的情況
        edge_index = torch.empty((2, 0), dtype=torch.long)
        print(f"[WARN]    圖形無邊")
    
    # 轉換特徵矩陣為張量
    x = torch.tensor(feature_matrix, dtype=torch.float32)
    
    # 創建 PyG Data 物件
    data = Data(x=x, edge_index=edge_index)
    
    # 附加元數據
    data.num_nodes = len(node_ids)
    data.node_ids = node_ids  # 保留原始 ID 供追溯
    data.node_to_idx = node_to_idx  # 保留映射關係
    
    # 特徵維度信息
    data.num_numerical_features = extractor.num_numerical_features
    data.num_categorical_features = extractor.num_categorical_features
    data.num_semantic_features = extractor.num_semantic_features
    
    print(f"\n[SUCCESS] 轉換完成:")
    print(f"[INFO]    節點數: {data.num_nodes}")
    print(f"[INFO]    邊數: {edge_index.shape[1]}")
    print(f"[INFO]    特徵維度: {data.x.shape[1]}")
    print(f"[INFO]    張量設備: {data.x.device}")
    print("="*60)
    
    return data


def handle_isolated_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    """
    處理孤立節點（無連接的節點）
    策略：為孤立節點添加預設屬性
    
    Args:
        graph: NetworkX 圖形
        
    Returns:
        處理後的圖形
    """
    isolated_nodes = list(nx.isolates(graph))
    
    if isolated_nodes:
        print(f"[INFO] 檢測到 {len(isolated_nodes)} 個孤立節點，正在添加預設屬性...")
        
        for node_id in isolated_nodes:
            if 'type' not in graph.nodes[node_id]:
                graph.nodes[node_id]['type'] = 'Other'
            if 'name' not in graph.nodes[node_id]:
                graph.nodes[node_id]['name'] = str(node_id)
    
    return graph


def impute_missing_attributes(graph: nx.DiGraph, 
                              default_values: Optional[Dict[str, Any]] = None) -> nx.DiGraph:
    """
    填補缺失的節點屬性
    
    Args:
        graph: NetworkX 圖形
        default_values: 預設值字典
        
    Returns:
        處理後的圖形
    """
    if default_values is None:
        default_values = {
            'type': 'Other',
            'name': 'unknown',
            'line_count': 0,
            'cyclomatic_complexity': 1,
            'parameters': []
        }
    
    print(f"[INFO] 正在填補缺失屬性...")
    modified_count = 0
    
    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        for attr, default_val in default_values.items():
            if attr not in node_data:
                node_data[attr] = default_val
                modified_count += 1
    
    if modified_count > 0:
        print(f"[INFO]    已填補 {modified_count} 個缺失屬性")
    
    return graph


def preprocess_graph(graph: nx.DiGraph) -> nx.DiGraph:
    """
    預處理圖形（整合所有預處理步驟）
    
    Args:
        graph: 原始 NetworkX 圖形
        
    Returns:
        預處理後的圖形
        
    Raises:
        TypeError: 如果輸入不是 NetworkX Graph 對象
    """
    # ✅ 型態檢查：確保輸入是 NetworkX 圖形
    import networkx as nx
    if not isinstance(graph, (nx.Graph, nx.DiGraph)):
        raise TypeError(
            f"[ERROR] preprocess_graph 預期收到 NetworkX Graph，"
            f"但收到的是 {type(graph).__name__}"
        )
    
    print("[INFO] 正在預處理圖形...")
    
    # 1. 處理孤立節點
    graph = handle_isolated_nodes(graph)
    
    # 2. 填補缺失屬性
    graph = impute_missing_attributes(graph)
    
    print("[SUCCESS] 預處理完成")
    
    return graph


if __name__ == "__main__":
    print("階段 3 特徵工程模組已就緒")
    print(f"支援的節點類型: {FeatureExtractor.NODE_TYPES}")
