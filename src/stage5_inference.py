"""
Stage 5: GNN Inference - 推論接口
加載訓練好的模型，對新數據進行預測，並整合到 Stage 4 可視化系統
"""

import torch
import torch.nn.functional as F
from torch_geometric.data import Data
import numpy as np
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

from src.stage5_model import OmniGAT, create_model

logger = logging.getLogger(__name__)


class BugPredictor:
    """
    Bug 預測器 - 加載訓練好的 OmniGAT 模型進行推論
    
    功能：
    - 加載 .pth 模型文件
    - 對單個節點或整個圖進行預測
    - 輸出 {node_id: probability} 映射
    - 生成 Stage 4 可視化所需的 JSON 格式
    """
    
    def __init__(
        self,
        model_path: str,
        device: str = 'cpu'
    ):
        """
        初始化預測器
        
        Args:
            model_path: 訓練好的模型路徑（.pth 文件）
            device: 計算設備
        """
        self.model_path = Path(model_path)
        self.device = device
        self.model = None
        self.model_config = None
        
        # 加載模型
        self._load_model()
    
    def _load_model(self):
        """加載訓練好的模型"""
        if not self.model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {self.model_path}")
        
        logger.info(f"加載模型: {self.model_path}")
        
        # 加載檢查點
        checkpoint = torch.load(self.model_path, map_location=self.device)
        
        # 獲取模型配置
        self.model_config = checkpoint.get('model_config', {})
        
        # 創建模型
        self.model = create_model(
            in_channels=self.model_config['in_channels'],
            config={
                'hidden_channels': self.model_config['hidden_channels'],
                'out_channels': self.model_config['out_channels'],
                'num_heads': self.model_config['num_heads'],
                'dropout': self.model_config.get('dropout', 0.3),
                'use_batch_norm': self.model_config.get('use_batch_norm', True)
            }
        )
        
        # 加載權重
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)
        self.model.eval()
        
        logger.info(f"模型加載成功")
        logger.info(f"  最佳驗證集 AUC: {checkpoint.get('best_val_auc', 'N/A')}")
        logger.info(f"  模型參數: {self.model.count_parameters():,}")
    
    @torch.no_grad()
    def predict(
        self,
        data: Data,
        return_attention: bool = False
    ) -> np.ndarray:
        """
        對整個圖進行預測
        
        Args:
            data: PyG Data 對象
            return_attention: 是否返回注意力權重
        
        Returns:
            predictions: 預測機率數組 [num_nodes]
            (可選) attention_weights: 注意力權重
        """
        self.model.eval()
        data = data.to(self.device)
        
        # 前向傳播
        if return_attention:
            out, attn_weights = self.model(
                data.x,
                data.edge_index,
                return_attention_weights=True
            )
        else:
            out = self.model(data.x, data.edge_index)
        
        # 提取預測機率
        predictions = out.squeeze().cpu().numpy()
        
        if return_attention:
            return predictions, attn_weights
        
        return predictions
    
    def predict_node(
        self,
        data: Data,
        node_id: int
    ) -> float:
        """
        預測單個節點的 Bug 機率
        
        Args:
            data: PyG Data 對象
            node_id: 節點 ID
        
        Returns:
            probability: Bug 機率（0-1 之間）
        """
        predictions = self.predict(data)
        
        if node_id >= len(predictions):
            raise ValueError(f"節點 ID {node_id} 超出範圍（總節點數: {len(predictions)}）")
        
        return float(predictions[node_id])
    
    def predict_batch(
        self,
        data: Data,
        node_ids: List[int]
    ) -> Dict[int, float]:
        """
        批量預測多個節點
        
        Args:
            data: PyG Data 對象
            node_ids: 節點 ID 列表
        
        Returns:
            predictions: {node_id: probability} 映射
        """
        all_predictions = self.predict(data)
        
        batch_predictions = {}
        for node_id in node_ids:
            if node_id < len(all_predictions):
                batch_predictions[node_id] = float(all_predictions[node_id])
            else:
                logger.warning(f"節點 ID {node_id} 超出範圍，跳過")
        
        return batch_predictions
    
    def predict_all(self, data: Data) -> Dict[int, float]:
        """
        預測所有節點
        
        Args:
            data: PyG Data 對象
        
        Returns:
            predictions: {node_id: probability} 映射
        """
        all_predictions = self.predict(data)
        
        return {
            int(node_id): float(prob)
            for node_id, prob in enumerate(all_predictions)
        }
    
    def get_high_risk_nodes(
        self,
        data: Data,
        threshold: float = 0.7,
        top_k: Optional[int] = None
    ) -> List[Tuple[int, float]]:
        """
        獲取高風險節點
        
        Args:
            data: PyG Data 對象
            threshold: 風險閾值（默認 0.7）
            top_k: 返回前 K 個最高風險節點（可選）
        
        Returns:
            high_risk_nodes: [(node_id, probability), ...] 按機率降序排列
        """
        predictions = self.predict(data)
        
        # 篩選高風險節點
        high_risk = [
            (int(node_id), float(prob))
            for node_id, prob in enumerate(predictions)
            if prob >= threshold
        ]
        
        # 按機率降序排列
        high_risk.sort(key=lambda x: x[1], reverse=True)
        
        # 限制返回數量
        if top_k is not None:
            high_risk = high_risk[:top_k]
        
        logger.info(f"檢測到 {len(high_risk)} 個高風險節點（閾值: {threshold}）")
        
        return high_risk
    
    def export_for_visualization(
        self,
        data: Data,
        output_path: str,
        include_metadata: bool = True
    ):
        """
        導出預測結果為 JSON 格式，供 Stage 4 可視化使用
        
        Args:
            data: PyG Data 對象
            output_path: 輸出文件路徑
            include_metadata: 是否包含元數據（模型配置、統計信息等）
        """
        predictions = self.predict(data)
        
        # 構建預測結果
        prediction_data = {
            "node_predictions": {
                str(node_id): float(prob)
                for node_id, prob in enumerate(predictions)
            },
            "num_nodes": len(predictions),
            "high_risk_count": int(np.sum(predictions >= 0.7)),
            "medium_risk_count": int(np.sum((predictions >= 0.4) & (predictions < 0.7))),
            "low_risk_count": int(np.sum(predictions < 0.4))
        }
        
        # 添加元數據
        if include_metadata:
            prediction_data["metadata"] = {
                "model_type": "OmniGAT",
                "model_config": self.model_config,
                "prediction_statistics": {
                    "mean": float(np.mean(predictions)),
                    "std": float(np.std(predictions)),
                    "min": float(np.min(predictions)),
                    "max": float(np.max(predictions)),
                    "median": float(np.median(predictions))
                }
            }
        
        # 保存文件
        output_path = Path(output_path)
        output_path.parent.mkdir(exist_ok=True, parents=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(prediction_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"預測結果已導出至: {output_path}")
        logger.info(f"  高風險節點: {prediction_data['high_risk_count']}")
        logger.info(f"  中風險節點: {prediction_data['medium_risk_count']}")
        logger.info(f"  低風險節點: {prediction_data['low_risk_count']}")
    
    def merge_with_graph_data(
        self,
        graph_data_path: str,
        output_path: str
    ):
        """
        將預測結果合併到 Stage 2 的圖數據中
        
        Args:
            graph_data_path: Stage 2 圖數據路徑（.pt 文件）
            output_path: 輸出路徑
        """
        # 加載圖數據
        graph_data = torch.load(graph_data_path)
        
        if not isinstance(graph_data, Data):
            logger.error("圖數據格式不正確")
            return
        
        # 預測
        predictions = self.predict(graph_data)
        
        # 添加預測結果到圖數據
        graph_data.predictions = torch.from_numpy(predictions).float()
        
        # 保存合併後的數據
        output_path = Path(output_path)
        output_path.parent.mkdir(exist_ok=True, parents=True)
        
        torch.save(graph_data, output_path)
        
        logger.info(f"預測結果已合併到圖數據並保存至: {output_path}")
    
    def analyze_predictions(
        self,
        data: Data,
        node_names: Optional[Dict[int, str]] = None
    ) -> Dict:
        """
        分析預測結果，生成統計報告
        
        Args:
            data: PyG Data 對象
            node_names: 節點 ID 到名稱的映射（可選）
        
        Returns:
            analysis: 分析結果字典
        """
        predictions = self.predict(data)
        
        # 基本統計
        analysis = {
            "total_nodes": len(predictions),
            "statistics": {
                "mean": float(np.mean(predictions)),
                "std": float(np.std(predictions)),
                "min": float(np.min(predictions)),
                "max": float(np.max(predictions)),
                "median": float(np.median(predictions)),
                "percentile_95": float(np.percentile(predictions, 95)),
                "percentile_99": float(np.percentile(predictions, 99))
            },
            "risk_distribution": {
                "high_risk (>= 0.7)": int(np.sum(predictions >= 0.7)),
                "medium_risk (0.4-0.7)": int(np.sum((predictions >= 0.4) & (predictions < 0.7))),
                "low_risk (< 0.4)": int(np.sum(predictions < 0.4))
            }
        }
        
        # Top 高風險節點
        top_k = 10
        top_indices = np.argsort(predictions)[-top_k:][::-1]
        
        top_risk_nodes = []
        for idx in top_indices:
            node_info = {
                "node_id": int(idx),
                "probability": float(predictions[idx])
            }
            if node_names and idx in node_names:
                node_info["name"] = node_names[idx]
            top_risk_nodes.append(node_info)
        
        analysis["top_risk_nodes"] = top_risk_nodes
        
        # 如果有真實標籤，計算評估指標
        if hasattr(data, 'y'):
            from sklearn.metrics import (
                accuracy_score, precision_score, recall_score,
                f1_score, roc_auc_score, confusion_matrix
            )
            
            y_true = data.y.cpu().numpy()
            y_pred = (predictions > 0.5).astype(int)
            
            analysis["evaluation"] = {
                "accuracy": float(accuracy_score(y_true, y_pred)),
                "precision": float(precision_score(y_true, y_pred, zero_division=0)),
                "recall": float(recall_score(y_true, y_pred, zero_division=0)),
                "f1_score": float(f1_score(y_true, y_pred, zero_division=0))
            }
            
            if len(np.unique(y_true)) > 1:
                analysis["evaluation"]["auc_roc"] = float(roc_auc_score(y_true, predictions))
            
            cm = confusion_matrix(y_true, y_pred)
            analysis["evaluation"]["confusion_matrix"] = {
                "true_negatives": int(cm[0, 0]),
                "false_positives": int(cm[0, 1]),
                "false_negatives": int(cm[1, 0]),
                "true_positives": int(cm[1, 1])
            }
        
        return analysis


def load_predictor(model_path: str, device: str = 'cpu') -> BugPredictor:
    """
    加載預測器（工廠函數）
    
    Args:
        model_path: 模型文件路徑
        device: 計算設備
    
    Returns:
        predictor: BugPredictor 實例
    """
    return BugPredictor(model_path, device)


if __name__ == "__main__":
    # 測試推論器
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("推論器測試")
    print("=" * 70)
    
    # 注意：此測試需要先運行訓練器生成模型文件
    # 這裡僅演示 API 使用方式
    
    model_path = "output/models/omni_gat_best.pth"
    
    if Path(model_path).exists():
        # 加載預測器
        predictor = load_predictor(model_path, device='cpu')
        
        # 創建測試數據
        num_nodes = 100
        in_channels = predictor.model_config['in_channels']
        num_edges = 300
        
        x = torch.randn(num_nodes, in_channels)
        edge_index = torch.randint(0, num_nodes, (2, num_edges))
        data = Data(x=x, edge_index=edge_index)
        
        # 預測所有節點
        print("\n1. 預測所有節點...")
        predictions = predictor.predict_all(data)
        print(f"   預測了 {len(predictions)} 個節點")
        
        # 獲取高風險節點
        print("\n2. 獲取高風險節點...")
        high_risk = predictor.get_high_risk_nodes(data, threshold=0.7, top_k=5)
        for node_id, prob in high_risk:
            print(f"   節點 {node_id}: {prob:.4f}")
        
        # 導出可視化數據
        print("\n3. 導出可視化數據...")
        predictor.export_for_visualization(
            data,
            "output/predictions/visualization_data.json"
        )
        
        # 分析預測結果
        print("\n4. 分析預測結果...")
        analysis = predictor.analyze_predictions(data)
        print(f"   風險分佈: {analysis['risk_distribution']}")
        
        print("\n[SUCCESS] 推論器測試通過")
    else:
        print(f"\n[WARN] 模型文件不存在: {model_path}")
        print("請先運行訓練器生成模型")
