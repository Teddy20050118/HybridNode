"""
Stage 5: GNN Trainer - 訓練邏輯與數據處理
處理類別不平衡、數據分割、訓練監控與模型驗證
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import Data
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, 
    f1_score, roc_auc_score, confusion_matrix
)
from typing import Dict, Tuple, Optional, List
import logging
from pathlib import Path
import json
import time
from datetime import datetime

from src.stage5_model import OmniGAT, create_model

logger = logging.getLogger(__name__)


class WeightedFocalLoss(nn.Module):
    """
    Weighted Focal Loss
    結合 Weighted Cross Entropy 和 Focal Loss，專為極度不平衡數據設計
    
    Args:
        alpha: 正樣本權重（0-1 之間）
        gamma: Focal Loss 參數（默認 2，gamma=0 時退化為 BCE）
    """
    
    def __init__(self, alpha: float = 0.75, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
    
    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        計算 Focal Loss
        
        Args:
            inputs: 預測機率 [N, 1]
            targets: 真實標籤 [N]
        
        Returns:
            loss: 標量
        """
        inputs = inputs.squeeze()
        targets = targets.float()
        
        # 計算 BCE Loss
        bce_loss = F.binary_cross_entropy(inputs, targets, reduction='none')
        
        # 計算 Focal Term: (1 - p_t)^gamma
        p_t = torch.where(targets == 1, inputs, 1 - inputs)
        focal_term = (1 - p_t) ** self.gamma
        
        # 計算 Alpha Weight
        alpha_t = torch.where(targets == 1, self.alpha, 1 - self.alpha)
        
        # 組合 Loss
        loss = alpha_t * focal_term * bce_loss
        
        return loss.mean()


class EarlyStopping:
    """
    早停機制（Early Stopping）
    當驗證集性能不再提升時停止訓練
    """
    
    def __init__(self, patience: int = 20, min_delta: float = 0.001):
        """
        Args:
            patience: 容忍的無改善輪數
            min_delta: 最小改善閾值
        """
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.best_epoch = 0
    
    def __call__(self, val_score: float, epoch: int) -> bool:
        """
        檢查是否應該早停
        
        Args:
            val_score: 驗證集分數（越高越好）
            epoch: 當前輪數
        
        Returns:
            是否應該停止訓練
        """
        if self.best_score is None:
            self.best_score = val_score
            self.best_epoch = epoch
        elif val_score < self.best_score + self.min_delta:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
                logger.info(f"早停觸發：驗證集分數 {self.patience} 輪未改善")
        else:
            self.best_score = val_score
            self.best_epoch = epoch
            self.counter = 0
        
        return self.early_stop


class OmniGATTrainer:
    """
    OmniGAT 訓練器
    
    功能：
    - 類別不平衡處理（Weighted Focal Loss）
    - 數據分割（Train/Val/Test Masks）
    - 訓練監控（Accuracy, Precision, Recall, AUC-ROC）
    - 梯度消失檢測
    - 過擬合警告
    - 注意力權重分析
    """
    
    def __init__(
        self,
        model: OmniGAT,
        data: Data,
        device: str = 'cpu',
        lr: float = 0.001,
        weight_decay: float = 5e-4,
        use_focal_loss: bool = True,
        focal_alpha: float = 0.75,
        focal_gamma: float = 2.0
    ):
        """
        初始化訓練器
        
        Args:
            model: OmniGAT 模型
            data: PyG Data 對象
            device: 計算設備
            lr: 學習率
            weight_decay: L2 正則化係數
            use_focal_loss: 是否使用 Focal Loss
            focal_alpha: Focal Loss 正樣本權重
            focal_gamma: Focal Loss gamma 參數
        """
        self.model = model.to(device)
        self.data = data.to(device)
        self.device = device
        self.lr = lr
        self.weight_decay = weight_decay
        
        # 損失函數
        if use_focal_loss:
            self.criterion = WeightedFocalLoss(alpha=focal_alpha, gamma=focal_gamma)
            logger.info(f"使用 Weighted Focal Loss (alpha={focal_alpha}, gamma={focal_gamma})")
        else:
            # 計算類別權重
            pos_weight = self._compute_class_weight()
            self.criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
            logger.info(f"使用 Weighted BCE Loss (pos_weight={pos_weight.item():.2f})")
        
        # 優化器
        self.optimizer = torch.optim.Adam(
            model.parameters(),
            lr=lr,
            weight_decay=weight_decay
        )
        
        # 學習率調度器
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            mode='max',
            factor=0.5,
            patience=10
        )
        
        # 訓練歷史
        self.history = {
            'train_loss': [],
            'train_acc': [],
            'val_loss': [],
            'val_acc': [],
            'val_precision': [],
            'val_recall': [],
            'val_f1': [],
            'val_auc': []
        }
        
        # 早停
        self.early_stopping = EarlyStopping(patience=20)
        
        # 最佳模型
        self.best_model_state = None
        self.best_val_auc = 0.0
        
        logger.info(f"訓練器初始化完成 (device={device}, lr={lr})")
    
    def _compute_class_weight(self) -> torch.Tensor:
        """
        計算類別權重（處理不平衡）
        
        Returns:
            pos_weight: 正樣本權重
        """
        if not hasattr(self.data, 'train_mask'):
            logger.warning("沒有 train_mask，無法計算類別權重，使用默認值 10.0")
            return torch.tensor([10.0]).to(self.device)
        
        train_labels = self.data.y[self.data.train_mask]
        num_pos = train_labels.sum().item()
        num_neg = len(train_labels) - num_pos
        
        if num_pos == 0:
            logger.warning("訓練集中沒有正樣本，使用默認權重")
            return torch.tensor([10.0]).to(self.device)
        
        pos_weight = num_neg / num_pos
        logger.info(f"類別分佈：正樣本={num_pos}, 負樣本={num_neg}, 權重比例={pos_weight:.2f}")
        
        return torch.tensor([pos_weight]).to(self.device)
    
    def train_epoch(self) -> Tuple[float, float]:
        """
        訓練一個 Epoch
        
        Returns:
            (loss, accuracy): 訓練損失和準確率
        """
        self.model.train()
        self.optimizer.zero_grad()
        
        # 前向傳播
        out = self.model(self.data.x, self.data.edge_index)
        
        # 計算損失（僅在訓練集上）
        loss = self.criterion(
            out[self.data.train_mask],
            self.data.y[self.data.train_mask]
        )
        
        # 反向傳播
        loss.backward()
        
        # 梯度裁剪（防止梯度爆炸）
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        
        self.optimizer.step()
        
        # 計算準確率
        pred = (out[self.data.train_mask] > 0.5).long().squeeze()
        true = self.data.y[self.data.train_mask].long()
        acc = (pred == true).float().mean().item()
        
        return loss.item(), acc
    
    @torch.no_grad()
    def evaluate(self, mask: torch.Tensor) -> Dict[str, float]:
        """
        在指定數據集上評估模型
        
        Args:
            mask: 數據集遮罩（train_mask/val_mask/test_mask）
        
        Returns:
            metrics: 評估指標字典
        """
        self.model.eval()
        
        # 前向傳播
        out = self.model(self.data.x, self.data.edge_index)
        
        # 計算損失
        loss = self.criterion(
            out[mask],
            self.data.y[mask]
        ).item()
        
        # 預測標籤與機率
        pred_probs = out[mask].squeeze().cpu().numpy()
        pred_labels = (pred_probs > 0.5).astype(int)
        true_labels = self.data.y[mask].cpu().numpy()
        
        # 計算指標
        metrics = {
            'loss': loss,
            'accuracy': accuracy_score(true_labels, pred_labels),
            'precision': precision_score(true_labels, pred_labels, zero_division=0),
            'recall': recall_score(true_labels, pred_labels, zero_division=0),
            'f1': f1_score(true_labels, pred_labels, zero_division=0)
        }
        
        # AUC-ROC（需要至少兩個類別）
        if len(np.unique(true_labels)) > 1:
            metrics['auc'] = roc_auc_score(true_labels, pred_probs)
        else:
            metrics['auc'] = 0.0
        
        # 混淆矩陣
        cm = confusion_matrix(true_labels, pred_labels)
        metrics['confusion_matrix'] = cm.tolist()
        
        return metrics
    
    def check_gradient_health(self) -> Dict[str, float]:
        """
        檢查梯度健康狀況（檢測梯度消失/爆炸）
        
        Returns:
            gradient_stats: 梯度統計信息
        """
        total_norm = 0.0
        max_grad = 0.0
        min_grad = float('inf')
        num_params = 0
        
        for p in self.model.parameters():
            if p.grad is not None:
                param_norm = p.grad.data.norm(2).item()
                total_norm += param_norm ** 2
                max_grad = max(max_grad, param_norm)
                min_grad = min(min_grad, param_norm)
                num_params += 1
        
        total_norm = total_norm ** 0.5
        
        stats = {
            'total_grad_norm': total_norm,
            'max_grad_norm': max_grad,
            'min_grad_norm': min_grad if min_grad != float('inf') else 0.0,
            'num_params_with_grad': num_params
        }
        
        # 梯度消失/爆炸警告
        if total_norm < 1e-6:
            logger.warning(f"[WARN] 梯度消失：總梯度範數 = {total_norm:.2e}")
        if total_norm > 10.0:
            logger.warning(f"[WARN] 梯度爆炸：總梯度範數 = {total_norm:.2f}")
        
        return stats
    
    def check_overfitting(self, train_acc: float, val_acc: float, threshold: float = 0.15):
        """
        檢查過擬合（訓練集與驗證集差距過大）
        
        Args:
            train_acc: 訓練集準確率
            val_acc: 驗證集準確率  
            threshold: 過擬合閾值（默認 15%）
        """
        gap = train_acc - val_acc
        if gap > threshold:
            logger.warning(
                f"[WARN] 過擬合警告：訓練集準確率 ({train_acc:.3f}) "
                f"遠高於驗證集 ({val_acc:.3f})，差距 {gap:.3f}"
            )
    
    def train(
        self,
        num_epochs: int = 200,
        verbose: int = 10,
        save_dir: Optional[str] = None
    ) -> Dict[str, List[float]]:
        """
        完整訓練流程
        
        Args:
            num_epochs: 訓練輪數
            verbose: 每隔多少輪輸出日誌
            save_dir: 模型保存目錄
        
        Returns:
            history: 訓練歷史
        """
        logger.info(f"開始訓練：{num_epochs} 輪")
        
        # 檢查數據分割
        if not hasattr(self.data, 'train_mask'):
            raise ValueError("數據缺少 train_mask，請先執行數據分割")
        
        start_time = time.time()
        
        for epoch in range(1, num_epochs + 1):
            # 訓練一輪
            train_loss, train_acc = self.train_epoch()
            
            # 驗證集評估
            if hasattr(self.data, 'val_mask'):
                val_metrics = self.evaluate(self.data.val_mask)
                val_loss = val_metrics['loss']
                val_acc = val_metrics['accuracy']
                val_auc = val_metrics['auc']
                
                # 更新學習率
                self.scheduler.step(val_auc)
                
                # 保存最佳模型
                if val_auc > self.best_val_auc:
                    self.best_val_auc = val_auc
                    self.best_model_state = self.model.state_dict().copy()
                
                # 早停檢查
                if self.early_stopping(val_auc, epoch):
                    logger.info(f"早停於第 {epoch} 輪（最佳輪數: {self.early_stopping.best_epoch}）")
                    break
                
                # 過擬合檢查
                if epoch % verbose == 0:
                    self.check_overfitting(train_acc, val_acc)
            else:
                val_loss = val_acc = val_auc = 0.0
                val_metrics = {}
            
            # 記錄歷史
            self.history['train_loss'].append(train_loss)
            self.history['train_acc'].append(train_acc)
            self.history['val_loss'].append(val_loss)
            self.history['val_acc'].append(val_acc)
            
            if val_metrics:
                self.history['val_precision'].append(val_metrics['precision'])
                self.history['val_recall'].append(val_metrics['recall'])
                self.history['val_f1'].append(val_metrics['f1'])
                self.history['val_auc'].append(val_auc)
            
            # 輸出日誌
            if epoch % verbose == 0 or epoch == 1:
                log_msg = (
                    f"Epoch {epoch:3d}/{num_epochs} | "
                    f"Train Loss: {train_loss:.4f}, Acc: {train_acc:.3f} | "
                )
                if val_metrics:
                    log_msg += (
                        f"Val Loss: {val_loss:.4f}, Acc: {val_acc:.3f}, "
                        f"P: {val_metrics['precision']:.3f}, "
                        f"R: {val_metrics['recall']:.3f}, "
                        f"F1: {val_metrics['f1']:.3f}, "
                        f"AUC: {val_auc:.3f}"
                    )
                logger.info(log_msg)
            
            # 第一輪：梯度健康檢查
            if epoch == 1:
                grad_stats = self.check_gradient_health()
                logger.info(f"梯度統計：{grad_stats}")
        
        # 訓練結束
        elapsed = time.time() - start_time
        logger.info(f"訓練完成，耗時: {elapsed:.1f}s")
        
        # 恢復最佳模型
        if self.best_model_state is not None:
            self.model.load_state_dict(self.best_model_state)
            logger.info(f"恢復最佳模型（驗證集 AUC: {self.best_val_auc:.4f}）")
        
        # 保存模型
        if save_dir:
            self.save_model(save_dir)
        
        return self.history
    
    def save_model(self, save_dir: str):
        """
        保存訓練好的模型
        
        Args:
            save_dir: 保存目錄
        """
        save_path = Path(save_dir)
        save_path.mkdir(exist_ok=True, parents=True)
        
        # 保存模型權重
        model_path = save_path / "omni_gat_best.pth"
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'model_config': self.model.get_model_info(),
            'best_val_auc': self.best_val_auc,
            'history': self.history
        }, model_path)
        
        logger.info(f"模型已保存至: {model_path}")
        
        # 保存訓練歷史
        history_path = save_path / "training_history.json"
        with open(history_path, 'w') as f:
            json.dump(self.history, f, indent=2)
        
        logger.info(f"訓練歷史已保存至: {history_path}")
    
    def analyze_attention_weights(self, top_k: int = 10) -> List[Tuple[int, int, float]]:
        """
        分析注意力權重，找出模型最關注的邊（高風險調用關係）
        
        Args:
            top_k: 返回前 K 個最重要的邊
        
        Returns:
            top_edges: [(源節點, 目標節點, 注意力分數), ...]
        """
        self.model.eval()
        
        with torch.no_grad():
            # 獲取注意力權重
            _, attn_weights = self.model(
                self.data.x,
                self.data.edge_index,
                return_attention_weights=True
            )
        
        if attn_weights is None:
            logger.warning("無法獲取注意力權重")
            return []
        
        # 使用第二層注意力（更接近最終預測）
        alpha = attn_weights[1].cpu().numpy()  # Shape: [num_edges_with_self_loops, num_heads]
        edge_index = self.data.edge_index.cpu().numpy()
        
        # 對多頭注意力求平均
        if alpha.ndim > 1:
            alpha_mean = alpha.mean(axis=1)  # 平均所有注意力頭
        else:
            alpha_mean = alpha
        
        # 注意：GATv2Conv 會添加自環，所以注意力權重可能比原始邊更多
        # 我們只取前 min(num_edges, len(alpha_mean)) 個
        num_valid_edges = min(edge_index.shape[1], len(alpha_mean))
        alpha_mean = alpha_mean[:num_valid_edges]
        
        # 找出權重最高的邊
        top_k_actual = min(top_k, num_valid_edges)
        top_indices = np.argsort(alpha_mean)[-top_k_actual:][::-1]
        
        top_edges = []
        for idx in top_indices:
            if idx < edge_index.shape[1]:
                src, dst = edge_index[:, idx]
                score = alpha_mean[idx]
                top_edges.append((int(src), int(dst), float(score)))
        
        logger.info(f"Top-{top_k} 高注意力權重的邊：")
        for src, dst, score in top_edges:
            logger.info(f"  {src} -> {dst}: {score:.4f}")
        
        return top_edges


def split_data(
    data: Data,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    stratify: bool = True,
    random_seed: int = 42
) -> Data:
    """
    分割圖數據為訓練集/驗證集/測試集
    
    Args:
        data: PyG Data 對象
        train_ratio: 訓練集比例
        val_ratio: 驗證集比例
        test_ratio: 測試集比例
        stratify: 是否分層採樣（保持正負樣本比例）
        random_seed: 隨機種子
    
    Returns:
        data: 添加了 train_mask, val_mask, test_mask 的 Data 對象
    """
    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6
    
    np.random.seed(random_seed)
    torch.manual_seed(random_seed)
    
    num_nodes = data.x.size(0)
    indices = np.arange(num_nodes)
    
    if stratify and hasattr(data, 'y'):
        # 分層採樣
        labels = data.y.cpu().numpy()
        pos_indices = np.where(labels == 1)[0]
        neg_indices = np.where(labels == 0)[0]
        
        # 分別對正負樣本進行分割
        np.random.shuffle(pos_indices)
        np.random.shuffle(neg_indices)
        
        n_pos_train = int(len(pos_indices) * train_ratio)
        n_pos_val = int(len(pos_indices) * val_ratio)
        
        n_neg_train = int(len(neg_indices) * train_ratio)
        n_neg_val = int(len(neg_indices) * val_ratio)
        
        train_indices = np.concatenate([
            pos_indices[:n_pos_train],
            neg_indices[:n_neg_train]
        ])
        val_indices = np.concatenate([
            pos_indices[n_pos_train:n_pos_train + n_pos_val],
            neg_indices[n_neg_train:n_neg_train + n_neg_val]
        ])
        test_indices = np.concatenate([
            pos_indices[n_pos_train + n_pos_val:],
            neg_indices[n_neg_train + n_neg_val:]
        ])
    else:
        # 隨機採樣
        np.random.shuffle(indices)
        
        n_train = int(num_nodes * train_ratio)
        n_val = int(num_nodes * val_ratio)
        
        train_indices = indices[:n_train]
        val_indices = indices[n_train:n_train + n_val]
        test_indices = indices[n_train + n_val:]
    
    # 創建遮罩
    train_mask = torch.zeros(num_nodes, dtype=torch.bool)
    val_mask = torch.zeros(num_nodes, dtype=torch.bool)
    test_mask = torch.zeros(num_nodes, dtype=torch.bool)
    
    train_mask[train_indices] = True
    val_mask[val_indices] = True
    test_mask[test_indices] = True
    
    data.train_mask = train_mask
    data.val_mask = val_mask
    data.test_mask = test_mask
    
    logger.info(f"數據分割完成：")
    logger.info(f"  訓練集: {train_mask.sum().item()} 節點")
    logger.info(f"  驗證集: {val_mask.sum().item()} 節點")
    logger.info(f"  測試集: {test_mask.sum().item()} 節點")
    
    if hasattr(data, 'y'):
        logger.info(f"  訓練集正樣本: {data.y[train_mask].sum().item()}")
        logger.info(f"  驗證集正樣本: {data.y[val_mask].sum().item()}")
        logger.info(f"  測試集正樣本: {data.y[test_mask].sum().item()}")
    
    return data


if __name__ == "__main__":
    # 測試訓練器
    from src.stage5_model import create_model
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 創建測試數據
    num_nodes = 200
    in_channels = 50
    num_edges = 800
    
    x = torch.randn(num_nodes, in_channels)
    edge_index = torch.randint(0, num_nodes, (2, num_edges))
    
    # 模擬不平衡標籤（10% 正樣本）
    y = torch.zeros(num_nodes)
    y[torch.randperm(num_nodes)[:20]] = 1
    
    data = Data(x=x, edge_index=edge_index, y=y)
    
    # 數據分割
    data = split_data(data)
    
    # 創建模型和訓練器
    model = create_model(in_channels)
    trainer = OmniGATTrainer(model, data, device='cpu')
    
    # 訓練
    print("\n開始訓練...")
    history = trainer.train(num_epochs=50, verbose=10)
    
    # 測試集評估
    print("\n測試集評估:")
    test_metrics = trainer.evaluate(data.test_mask)
    for key, value in test_metrics.items():
        if key != 'confusion_matrix':
            print(f"  {key}: {value:.4f}")
    
    # 注意力權重分析
    print("\n注意力權重分析:")
    top_edges = trainer.analyze_attention_weights(top_k=5)
    
    print("\n[SUCCESS] 訓練器測試通過")
