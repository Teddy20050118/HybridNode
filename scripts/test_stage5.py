"""
Stage 5 完整測試腳本
演示模型訓練和推論的完整流程
"""

import sys
import os
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import torch
import numpy as np
from torch_geometric.data import Data

from src.stage5_model import create_model
from src.stage5_trainer import OmniGATTrainer, split_data
from src.stage5_inference import BugPredictor


def create_synthetic_data(num_nodes=200, num_edges=800, in_channels=50, pos_ratio=0.1):
    """創建合成測試數據"""
    print(f"創建合成數據：{num_nodes} 個節點，{num_edges} 條邊")
    
    # 節點特徵（隨機）
    x = torch.randn(num_nodes, in_channels)
    
    # 邊索引（隨機連接）
    edge_index = torch.randint(0, num_nodes, (2, num_edges))
    
    # 標籤（不平衡：10% 正樣本）
    y = torch.zeros(num_nodes)
    num_pos = int(num_nodes * pos_ratio)
    y[torch.randperm(num_nodes)[:num_pos]] = 1
    
    data = Data(x=x, edge_index=edge_index, y=y)
    
    print(f"  特徵維度: {x.shape}")
    print(f"  正樣本數: {y.sum().item()} ({y.sum().item()/len(y)*100:.1f}%)")
    
    return data


def test_training():
    """測試訓練流程"""
    print("\n" + "=" * 70)
    print("測試 1：模型訓練")
    print("=" * 70)
    
    # 創建數據
    data = create_synthetic_data(num_nodes=200, num_edges=800)
    
    # 數據分割
    print("\n數據分割...")
    data = split_data(data, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
    
    # 創建模型
    print("\n創建模型...")
    model = create_model(
        in_channels=data.x.shape[1],
        config={'hidden_channels': 32, 'num_heads': 2, 'dropout': 0.2}
    )
    
    print(f"  模型參數: {model.count_parameters():,}")
    
    # 創建訓練器
    print("\n初始化訓練器...")
    trainer = OmniGATTrainer(
        model=model,
        data=data,
        device='cpu',
        lr=0.005,
        use_focal_loss=True
    )
    
    # 訓練（少量輪數用於測試）
    print("\n開始訓練（30 輪）...")
    history = trainer.train(num_epochs=30, verbose=10, save_dir=None)
    
    # 測試集評估
    print("\n測試集評估：")
    test_metrics = trainer.evaluate(data.test_mask)
    
    print(f"  準確率:  {test_metrics['accuracy']:.4f}")
    print(f"  精確率:  {test_metrics['precision']:.4f}")
    print(f"  召回率:  {test_metrics['recall']:.4f}")
    print(f"  F1 分數: {test_metrics['f1']:.4f}")
    print(f"  AUC-ROC: {test_metrics['auc']:.4f}")
    
    # 注意力權重分析
    print("\n注意力權重分析：")
    top_edges = trainer.analyze_attention_weights(top_k=5)
    
    print("\n✅ 訓練測試通過")
    
    return model, data


def test_inference(model, data):
    """測試推論流程"""
    print("\n" + "=" * 70)
    print("測試 2：模型推論")
    print("=" * 70)
    
    # 保存模型到臨時文件
    temp_model_path = "test_model.pth"
    torch.save({
        'model_state_dict': model.state_dict(),
        'model_config': model.get_model_info(),
        'best_val_auc': 0.85
    }, temp_model_path)
    
    print(f"模型已保存至: {temp_model_path}")
    
    # 加載預測器
    print("\n加載預測器...")
    predictor = BugPredictor(temp_model_path, device='cpu')
    
    # 預測所有節點
    print("\n執行預測...")
    predictions = predictor.predict_all(data)
    
    print(f"  預測了 {len(predictions)} 個節點")
    
    # 獲取高風險節點
    print("\n高風險節點（Top-5）：")
    high_risk = predictor.get_high_risk_nodes(data, threshold=0.6, top_k=5)
    
    for i, (node_id, prob) in enumerate(high_risk, 1):
        print(f"  {i}. 節點 {node_id:3d}: {prob:.4f}")
    
    # 分析預測結果
    print("\n預測分析：")
    analysis = predictor.analyze_predictions(data)
    
    print(f"  風險分佈:")
    for risk_level, count in analysis['risk_distribution'].items():
        print(f"    {risk_level}: {count}")
    
    # 清理臨時文件
    os.remove(temp_model_path)
    print(f"\n臨時文件已清理: {temp_model_path}")
    
    print("\n✅ 推論測試通過")


def test_attention_analysis(model, data):
    """測試注意力權重分析"""
    print("\n" + "=" * 70)
    print("測試 3：注意力權重分析")
    print("=" * 70)
    
    model.eval()
    
    with torch.no_grad():
        # 獲取注意力權重
        out, attn_weights = model(
            data.x,
            data.edge_index,
            return_attention_weights=True
        )
    
    print(f"第一層注意力權重形狀: {attn_weights[0].shape}")
    print(f"第二層注意力權重形狀: {attn_weights[1].shape}")
    
    # 分析注意力分佈
    alpha_layer2 = attn_weights[1].numpy()
    
    print(f"\n注意力權重統計：")
    print(f"  平均值: {np.mean(alpha_layer2):.4f}")
    print(f"  標準差: {np.std(alpha_layer2):.4f}")
    print(f"  最小值: {np.min(alpha_layer2):.4f}")
    print(f"  最大值: {np.max(alpha_layer2):.4f}")
    
    # 對多頭注意力求平均
    if alpha_layer2.ndim > 1:
        alpha_mean = alpha_layer2.mean(axis=1)
    else:
        alpha_mean = alpha_layer2
    
    # 找出最重要的邊（確保不超出邊索引範圍）
    top_k = 5
    num_valid_edges = min(data.edge_index.shape[1], len(alpha_mean))
    alpha_valid = alpha_mean[:num_valid_edges]
    top_indices = np.argsort(alpha_valid)[-top_k:][::-1]
    
    print(f"\nTop-{top_k} 重要的邊：")
    for i, idx in enumerate(top_indices, 1):
        src, dst = data.edge_index[:, idx].tolist()
        score = alpha_valid[idx]
        print(f"  {i}. 邊 {idx:3d} ({src:3d} → {dst:3d}): {score:.4f}")
    
    print("\n✅ 注意力分析測試通過")


def main():
    """主測試函數"""
    print("=" * 70)
    print(" " * 20 + "Stage 5 完整測試")
    print("=" * 70)
    
    try:
        # 測試 1：訓練
        model, data = test_training()
        
        # 測試 2：推論
        test_inference(model, data)
        
        # 測試 3：注意力分析
        test_attention_analysis(model, data)
        
        # 總結
        print("\n" + "=" * 70)
        print(" " * 20 + "所有測試通過！")
        print("=" * 70)
        
        print("\n✅ Stage 5 系統完全就緒")
        print("\n下一步：")
        print("  1. 使用真實數據訓練模型：python scripts/train_model.py")
        print("  2. 使用模型進行預測：python scripts/predict.py")
        print("  3. 查看完整文檔：docs/STAGE5_COMPLETION_REPORT.md")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ 測試失敗：{str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
