"""
階段 3：AI 特徵工程 (Feature Engineering)
功能：將 NetworkX 圖形轉換為 PyTorch Geometric 可訓練的張量格式
"""

import os

# 設定環境變數（必須在 import torch 之前完成）
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

print("[INFO] [Stage3] 環境變數執行緒限制已全部設定完畢")

import warnings
warnings.filterwarnings('ignore')

print("[INFO] [Stage3] 準備匯入 torch...")
import torch
print("[INFO] [Stage3] torch 匯入成功")

# 設定 PyTorch 執行緒限制
try:
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass
torch.backends.cudnn.enabled = False

import numpy as np
import networkx as nx
from torch_geometric.data import Data
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from typing import Dict, List, Tuple, Optional, Any
import hashlib

print("[INFO] [Stage3] 所有基礎模組匯入完成")

_FALLBACK_EMBEDDING_DIM = 384

def _hash_embedding(text: str, dim: int = _FALLBACK_EMBEDDING_DIM) -> np.ndarray:
    """以輕量級 SHA-256 雜湊演算法產生確定性向量"""
    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
    seed_int = int.from_bytes(seed_bytes[:4], "big")
    rng = np.random.default_rng(seed_int)
    vec = rng.uniform(-1.0, 1.0, size=dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 1e-8:
        vec = vec / norm
    return vec

class _DummyEmbeddingModel:
    """虛擬語義嵌入模型，在正式模型載入失敗時作為備用"""
    def __init__(self, dim: int = _FALLBACK_EMBEDDING_DIM):
        self._dim = dim
        print(f"[WARN] [Stage3] 啟動降級模式：使用備用語義特徵（雜湊向量，維度={dim}）")

    def encode(self, text: str, convert_to_numpy: bool = True,
               show_progress_bar: bool = False) -> np.ndarray:
        return _hash_embedding(text, self._dim)

    def get_sentence_embedding_dimension(self) -> int:
        return self._dim

class FeatureExtractor:
    NODE_TYPES = ['FunctionDecl', 'CXXRecordDecl', 'VarDecl', 'ExternalReference', 'Other']

    def __init__(self,
                 embedding_model: str = 'all-MiniLM-L6-v2',
                 scaler_type: str = 'standard',
                 use_cache: bool = True):
                 
        print("[INFO] [Stage3] ========== FeatureExtractor.__init__ 開始 ==========")
        
        # 直接在當前執行緒中載入模型，絕對禁止跨執行緒！
        print(f"[INFO] [Stage3] 準備載入語義嵌入模型: '{embedding_model}'")
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer(embedding_model, device="cpu")
            print("[SUCCESS] [Stage3] 正式語義模型載入成功！")
        except Exception as e:
            print(f"[ERROR] [Stage3] 模型載入失敗: {e}")
            self.embedding_model = _DummyEmbeddingModel(dim=_FALLBACK_EMBEDDING_DIM)

        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        print(f"[INFO] [Stage3] embedding_dim = {self.embedding_dim}")

        if scaler_type == 'standard':
            self.scaler = StandardScaler()
        elif scaler_type == 'minmax':
            self.scaler = MinMaxScaler()
        else:
            raise ValueError(f"不支援的縮放類型: {scaler_type}")

        self.use_cache = use_cache
        self.embedding_cache: Dict[str, np.ndarray] = {}

        self.num_numerical_features = 5
        self.num_categorical_features = len(self.NODE_TYPES)
        self.num_semantic_features = self.embedding_dim
        self.total_feature_dim = (
            self.num_numerical_features +
            self.num_categorical_features +
            self.num_semantic_features
        )
        print("[INFO] [Stage3] ========== FeatureExtractor.__init__ 完成 ==========")

    def extract_numerical_features(self, node_data: Dict) -> np.ndarray:
        lines_of_code = float(node_data.get('line_count', 0))
        complexity = float(node_data.get('cyclomatic_complexity', 1))
        parameters = node_data.get('parameters', [])
        param_count = float(len(parameters)) if isinstance(parameters, list) else 0.0
        return np.array([lines_of_code, complexity, param_count], dtype=np.float32)

    def extract_categorical_features(self, node_data: Dict) -> np.ndarray:
        node_type = node_data.get('type', 'Other')
        one_hot = np.zeros(len(self.NODE_TYPES), dtype=np.float32)
        try:
            idx = self.NODE_TYPES.index(node_type)
            one_hot[idx] = 1.0
        except ValueError:
            idx = self.NODE_TYPES.index('Other')
            one_hot[idx] = 1.0
        return one_hot

    def extract_semantic_features(self, node_data: Dict) -> np.ndarray:
        name = node_data.get('name', node_data.get('id', 'unknown'))
        if self.use_cache and name in self.embedding_cache:
            return self.embedding_cache[name]

        node_type = node_data.get('type', 'unknown')
        text = f"{node_type} {name}"

        try:
            embedding = self.embedding_model.encode(
                text, convert_to_numpy=True, show_progress_bar=False
            )
            embedding = np.asarray(embedding, dtype=np.float32)
        except Exception as exc:
            print(f"[WARN] [Stage3] encode() 呼叫失敗，回傳全零向量。原因: {exc}")
            embedding = np.zeros(self.embedding_dim, dtype=np.float32)

        if self.use_cache:
            self.embedding_cache[name] = embedding
        return embedding

    def extract_structural_features(self, graph: nx.DiGraph, node_id: str) -> np.ndarray:
        in_degree = float(graph.in_degree(node_id))
        out_degree = float(graph.out_degree(node_id))
        return np.array([in_degree, out_degree], dtype=np.float32)

    def extract_node_features(self, graph: nx.DiGraph, node_id: str) -> np.ndarray:
        node_data = graph.nodes[node_id]
        numerical = self.extract_numerical_features(node_data)
        structural = self.extract_structural_features(graph, node_id)
        numerical_all = np.concatenate([numerical, structural])
        categorical = self.extract_categorical_features(node_data)
        semantic = self.extract_semantic_features(node_data)
        
        feature_vector = np.concatenate([
            numerical_all, categorical, semantic
        ])
        return feature_vector

    def build_feature_matrix(self, graph: nx.DiGraph) -> Tuple[np.ndarray, List[str]]:
        print(f"\n[INFO] [Stage3] 正在提取圖形特徵...")
        node_ids = sorted(list(graph.nodes()))
        num_nodes = len(node_ids)
        feature_matrix = np.zeros((num_nodes, self.total_feature_dim), dtype=np.float32)

        for idx, node_id in enumerate(node_ids):
            feature_matrix[idx] = self.extract_node_features(graph, node_id)

        if feature_matrix.size == 0:
            return feature_matrix, node_ids

        numerical_features = feature_matrix[:, :self.num_numerical_features]
        non_zero_mask = np.any(numerical_features != 0, axis=1)
        if non_zero_mask.any():
            scaled_features = numerical_features.copy()
            scaled_features[non_zero_mask] = self.scaler.fit_transform(
                numerical_features[non_zero_mask]
            )
            feature_matrix[:, :self.num_numerical_features] = scaled_features

        return feature_matrix, node_ids

def to_pyg_data(graph: nx.DiGraph,
                extractor: Optional[FeatureExtractor] = None,
                include_edge_attr: bool = False) -> Data:
    if extractor is None:
        extractor = FeatureExtractor()

    feature_matrix, node_ids = extractor.build_feature_matrix(graph)

    if len(node_ids) == 0:
        empty_data = Data(
            x=torch.zeros((0, extractor.total_feature_dim), dtype=torch.float32),
            edge_index=torch.empty((2, 0), dtype=torch.long),
        )
        empty_data.num_nodes = 0
        empty_data.node_ids = []
        return empty_data

    node_to_idx = {node_id: idx for idx, node_id in enumerate(node_ids)}
    
    edge_list = []
    for u, v, edge_data in graph.edges(data=True):
        if u in node_to_idx and v in node_to_idx:
            edge_list.append([node_to_idx[u], node_to_idx[v]])

    if len(edge_list) > 0:
        edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)

    x = torch.tensor(feature_matrix, dtype=torch.float32)
    data = Data(x=x, edge_index=edge_index)
    
    data.num_nodes = len(node_ids)
    data.node_ids = node_ids
    data.node_to_idx = node_to_idx

    print(f"[SUCCESS] [Stage3] 轉換 PyG 格式完成")
    return data

def handle_isolated_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    isolated_nodes = list(nx.isolates(graph))
    if isolated_nodes:
        for node_id in isolated_nodes:
            if 'type' not in graph.nodes[node_id]:
                graph.nodes[node_id]['type'] = 'Other'
            if 'name' not in graph.nodes[node_id]:
                graph.nodes[node_id]['name'] = str(node_id)
    return graph

def impute_missing_attributes(graph: nx.DiGraph) -> nx.DiGraph:
    default_values = {
        'type': 'Other', 'name': 'unknown', 'line_count': 0,
        'cyclomatic_complexity': 1, 'parameters': []
    }
    for node_id in graph.nodes():
        node_data = graph.nodes[node_id]
        for attr, default_val in default_values.items():
            if attr not in node_data:
                node_data[attr] = default_val
    return graph

def preprocess_graph(graph: nx.DiGraph) -> nx.DiGraph:
    if not isinstance(graph, (nx.Graph, nx.DiGraph)):
        raise TypeError("[ERROR] 預期收到 NetworkX Graph")
    graph = handle_isolated_nodes(graph)
    graph = impute_missing_attributes(graph)
    return graph