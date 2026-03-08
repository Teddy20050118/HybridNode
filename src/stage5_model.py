"""
Stage 5: GNN-based Bug Prediction Model
實作 OmniGAT 模型 - 基於 GATv2Conv 的污染預測模型
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATv2Conv, global_mean_pool
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class OmniGAT(nn.Module):
    """
    OmniGAT: Graph Attention Network for Bug Prediction
    
    架構：
    - 兩層 GATv2Conv（改進的 GAT，具備動態注意力權重）
    - 多頭注意力機制（Multi-Head Attention）
    - Batch Normalization 穩定訓練
    - Dropout 防止過擬合
    - Sigmoid 輸出層（污染機率 0-1）
    
    Args:
        in_channels: 輸入節點特徵維度
        hidden_channels: 隱藏層維度
        out_channels: 輸出維度（默認 1，二分類）
        num_heads: 注意力頭數（默認 4）
        dropout: Dropout 比例（默認 0.3）
        use_batch_norm: 是否使用 Batch Normalization（默認 True）
    """
    
    def __init__(
        self,
        in_channels: int,
        hidden_channels: int = 64,
        out_channels: int = 1,
        num_heads: int = 4,
        dropout: float = 0.3,
        use_batch_norm: bool = True
    ):
        super(OmniGAT, self).__init__()
        
        self.in_channels = in_channels
        self.hidden_channels = hidden_channels
        self.out_channels = out_channels
        self.num_heads = num_heads
        self.dropout = dropout
        self.use_batch_norm = use_batch_norm
        
        # 第一層 GAT（多頭注意力）
        self.conv1 = GATv2Conv(
            in_channels=in_channels,
            out_channels=hidden_channels,
            heads=num_heads,
            dropout=dropout,
            concat=True,  # 拼接多頭輸出
            edge_dim=None  # 可擴展：添加邊特徵
        )
        
        # 第一層 Batch Normalization
        if use_batch_norm:
            self.bn1 = nn.BatchNorm1d(hidden_channels * num_heads)
        
        # 第二層 GAT（單頭輸出，用於最終預測）
        self.conv2 = GATv2Conv(
            in_channels=hidden_channels * num_heads,
            out_channels=hidden_channels,
            heads=num_heads,
            dropout=dropout,
            concat=False,  # 平均多頭輸出
            edge_dim=None
        )
        
        # 第二層 Batch Normalization
        if use_batch_norm:
            self.bn2 = nn.BatchNorm1d(hidden_channels)
        
        # 輸出層（全連接層）
        self.fc_out = nn.Linear(hidden_channels, out_channels)
        
        # Dropout 層
        self.dropout_layer = nn.Dropout(dropout)
        
        # 記錄注意力權重（用於分析）
        self.attention_weights = None
        
        logger.info(f"初始化 OmniGAT 模型：")
        logger.info(f"  輸入維度: {in_channels}")
        logger.info(f"  隱藏維度: {hidden_channels}")
        logger.info(f"  注意力頭數: {num_heads}")
        logger.info(f"  Dropout: {dropout}")
        logger.info(f"  Batch Normalization: {use_batch_norm}")
    
    def forward(
        self, 
        x: torch.Tensor, 
        edge_index: torch.Tensor,
        return_attention_weights: bool = False
    ) -> torch.Tensor:
        """
        前向傳播
        
        Args:
            x: 節點特徵矩陣 [num_nodes, in_channels]
            edge_index: 邊索引 [2, num_edges]
            return_attention_weights: 是否返回注意力權重
        
        Returns:
            out: 預測機率 [num_nodes, 1]
            (可選) attention_weights: 注意力權重
        """
        # 第一層 GAT + Activation + Dropout
        if return_attention_weights:
            x, (edge_index_1, alpha_1) = self.conv1(
                x, edge_index, return_attention_weights=True
            )
        else:
            x = self.conv1(x, edge_index)
        
        # Batch Normalization
        if self.use_batch_norm:
            x = self.bn1(x)
        
        # ELU 激活函數（更適合 GAT）
        x = F.elu(x)
        x = self.dropout_layer(x)
        
        # 第二層 GAT + Activation + Dropout
        if return_attention_weights:
            x, (edge_index_2, alpha_2) = self.conv2(
                x, edge_index, return_attention_weights=True
            )
            # 保存注意力權重
            self.attention_weights = (alpha_1, alpha_2)
        else:
            x = self.conv2(x, edge_index)
        
        # Batch Normalization
        if self.use_batch_norm:
            x = self.bn2(x)
        
        x = F.elu(x)
        x = self.dropout_layer(x)
        
        # 輸出層 + Sigmoid（污染機率）
        x = self.fc_out(x)
        out = torch.sigmoid(x)
        
        if return_attention_weights:
            return out, self.attention_weights
        
        return out
    
    def get_attention_weights(self) -> Optional[Tuple[torch.Tensor, torch.Tensor]]:
        """
        獲取最後一次前向傳播的注意力權重
        
        Returns:
            (alpha_1, alpha_2): 兩層的注意力權重
        """
        return self.attention_weights
    
    def reset_parameters(self):
        """重置模型參數（Xavier 初始化）"""
        self.conv1.reset_parameters()
        self.conv2.reset_parameters()
        
        # 初始化輸出層
        nn.init.xavier_uniform_(self.fc_out.weight)
        nn.init.zeros_(self.fc_out.bias)
        
        logger.info("模型參數已重置")
    
    def count_parameters(self) -> int:
        """計算可訓練參數數量"""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
    
    def get_model_info(self) -> dict:
        """獲取模型信息"""
        return {
            "model_name": "OmniGAT",
            "in_channels": self.in_channels,
            "hidden_channels": self.hidden_channels,
            "out_channels": self.out_channels,
            "num_heads": self.num_heads,
            "dropout": self.dropout,
            "use_batch_norm": self.use_batch_norm,
            "total_parameters": self.count_parameters(),
            "trainable_parameters": sum(
                p.numel() for p in self.parameters() if p.requires_grad
            )
        }


class OmniGATWithEdgeFeatures(OmniGAT):
    """
    擴展版 OmniGAT，支援邊特徵（Edge Features）
    可用於建模「函數調用類型」、「調用頻率」等邊屬性
    
    Args:
        edge_dim: 邊特徵維度
        其他參數同 OmniGAT
    """
    
    def __init__(
        self,
        in_channels: int,
        edge_dim: int = 1,
        hidden_channels: int = 64,
        out_channels: int = 1,
        num_heads: int = 4,
        dropout: float = 0.3,
        use_batch_norm: bool = True
    ):
        # 覆寫父類初始化前先保存 edge_dim
        self.edge_dim = edge_dim
        
        # 先初始化基礎屬性
        nn.Module.__init__(self)
        self.in_channels = in_channels
        self.hidden_channels = hidden_channels
        self.out_channels = out_channels
        self.num_heads = num_heads
        self.dropout = dropout
        self.use_batch_norm = use_batch_norm
        
        # 第一層 GAT（支援邊特徵）
        self.conv1 = GATv2Conv(
            in_channels=in_channels,
            out_channels=hidden_channels,
            heads=num_heads,
            dropout=dropout,
            concat=True,
            edge_dim=edge_dim  # 關鍵：添加邊特徵維度
        )
        
        if use_batch_norm:
            self.bn1 = nn.BatchNorm1d(hidden_channels * num_heads)
        
        # 第二層 GAT
        self.conv2 = GATv2Conv(
            in_channels=hidden_channels * num_heads,
            out_channels=hidden_channels,
            heads=num_heads,
            dropout=dropout,
            concat=False,
            edge_dim=edge_dim
        )
        
        if use_batch_norm:
            self.bn2 = nn.BatchNorm1d(hidden_channels)
        
        self.fc_out = nn.Linear(hidden_channels, out_channels)
        self.dropout_layer = nn.Dropout(dropout)
        self.attention_weights = None
        
        logger.info(f"初始化 OmniGATWithEdgeFeatures 模型（邊特徵維度: {edge_dim}）")
    
    def forward(
        self, 
        x: torch.Tensor, 
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None,
        return_attention_weights: bool = False
    ) -> torch.Tensor:
        """
        前向傳播（支援邊特徵）
        
        Args:
            x: 節點特徵矩陣 [num_nodes, in_channels]
            edge_index: 邊索引 [2, num_edges]
            edge_attr: 邊特徵矩陣 [num_edges, edge_dim]
            return_attention_weights: 是否返回注意力權重
        
        Returns:
            out: 預測機率 [num_nodes, 1]
        """
        # 第一層
        if return_attention_weights:
            x, (edge_index_1, alpha_1) = self.conv1(
                x, edge_index, edge_attr=edge_attr, return_attention_weights=True
            )
        else:
            x = self.conv1(x, edge_index, edge_attr=edge_attr)
        
        if self.use_batch_norm:
            x = self.bn1(x)
        x = F.elu(x)
        x = self.dropout_layer(x)
        
        # 第二層
        if return_attention_weights:
            x, (edge_index_2, alpha_2) = self.conv2(
                x, edge_index, edge_attr=edge_attr, return_attention_weights=True
            )
            self.attention_weights = (alpha_1, alpha_2)
        else:
            x = self.conv2(x, edge_index, edge_attr=edge_attr)
        
        if self.use_batch_norm:
            x = self.bn2(x)
        x = F.elu(x)
        x = self.dropout_layer(x)
        
        # 輸出層
        x = self.fc_out(x)
        out = torch.sigmoid(x)
        
        if return_attention_weights:
            return out, self.attention_weights
        
        return out


def create_model(in_channels: int, config: dict = None) -> OmniGAT:
    """
    工廠函數：根據配置創建模型
    
    Args:
        in_channels: 輸入特徵維度
        config: 模型配置字典
    
    Returns:
        model: OmniGAT 模型實例
    """
    if config is None:
        config = {}
    
    model = OmniGAT(
        in_channels=in_channels,
        hidden_channels=config.get('hidden_channels', 64),
        out_channels=config.get('out_channels', 1),
        num_heads=config.get('num_heads', 4),
        dropout=config.get('dropout', 0.3),
        use_batch_norm=config.get('use_batch_norm', True)
    )
    
    logger.info(f"創建模型成功，總參數: {model.count_parameters():,}")
    
    return model


if __name__ == "__main__":
    # 測試模型
    logging.basicConfig(level=logging.INFO)
    
    # 創建測試數據
    num_nodes = 100
    in_channels = 50
    num_edges = 300
    
    x = torch.randn(num_nodes, in_channels)
    edge_index = torch.randint(0, num_nodes, (2, num_edges))
    
    # 創建模型
    model = create_model(in_channels)
    print("\n模型信息:")
    for key, value in model.get_model_info().items():
        print(f"  {key}: {value}")
    
    # 測試前向傳播
    print("\n測試前向傳播...")
    model.eval()
    with torch.no_grad():
        out = model(x, edge_index)
        print(f"輸出形狀: {out.shape}")
        print(f"輸出範圍: [{out.min().item():.4f}, {out.max().item():.4f}]")
    
    # 測試注意力權重
    print("\n測試注意力權重...")
    with torch.no_grad():
        out, attn_weights = model(x, edge_index, return_attention_weights=True)
        print(f"第一層注意力權重形狀: {attn_weights[0].shape}")
        print(f"第二層注意力權重形狀: {attn_weights[1].shape}")
    
    print("\n[SUCCESS] 模型測試通過")
