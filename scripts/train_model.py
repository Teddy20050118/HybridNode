"""
Stage 5 訓練腳本
獨立訓練 OmniGAT 模型的快速腳本
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import torch
from src.stage5_model import create_model
from src.stage5_trainer import OmniGATTrainer, split_data

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """解析命令行參數"""
    parser = argparse.ArgumentParser(
        description='OmniGAT 模型訓練腳本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  # 基本訓練（使用默認參數）
  python scripts/train_model.py
  
  # 自定義訓練參數
  python scripts/train_model.py --epochs 300 --lr 0.005 --hidden-dim 128
  
  # 使用 GPU 訓練
  python scripts/train_model.py --device cuda
  
  # 自定義數據路徑
  python scripts/train_model.py --graph-data output/graph_data.pt --output output/models
        """
    )
    
    # 數據與輸出
    parser.add_argument('--graph-data', default='output/graph_data.pt',
                        help='PyG 圖數據路徑（默認：output/graph_data.pt）')
    parser.add_argument('--output', '-o', default='output/models',
                        help='模型保存目錄（默認：output/models）')
    
    # 模型配置
    parser.add_argument('--hidden-dim', type=int, default=64,
                        help='隱藏層維度（默認：64）')
    parser.add_argument('--num-heads', type=int, default=4,
                        help='注意力頭數（默認：4）')
    parser.add_argument('--dropout', type=float, default=0.3,
                        help='Dropout 比例（默認：0.3）')
    
    # 訓練配置
    parser.add_argument('--epochs', type=int, default=200,
                        help='訓練輪數（默認：200）')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='學習率（默認：0.001）')
    parser.add_argument('--weight-decay', type=float, default=5e-4,
                        help='L2 正則化係數（默認：5e-4）')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu',
                        help='計算設備（默認：cpu）')
    
    # 數據分割
    parser.add_argument('--train-ratio', type=float, default=0.6,
                        help='訓練集比例（默認：0.6）')
    parser.add_argument('--val-ratio', type=float, default=0.2,
                        help='驗證集比例（默認：0.2）')
    parser.add_argument('--test-ratio', type=float, default=0.2,
                        help='測試集比例（默認：0.2）')
    parser.add_argument('--random-seed', type=int, default=42,
                        help='隨機種子（默認：42）')
    
    # 損失函數
    parser.add_argument('--use-focal-loss', action='store_true', default=True,
                        help='使用 Focal Loss（默認：True）')
    parser.add_argument('--focal-alpha', type=float, default=0.75,
                        help='Focal Loss alpha 參數（默認：0.75）')
    parser.add_argument('--focal-gamma', type=float, default=2.0,
                        help='Focal Loss gamma 參數（默認：2.0）')
    
    # 其他選項
    parser.add_argument('--verbose', type=int, default=10,
                        help='每隔多少輪輸出日誌（默認：10）')
    parser.add_argument('--analyze-attention', action='store_true',
                        help='訓練後分析注意力權重')
    
    return parser.parse_args()


def main():
    """主函數"""
    args = parse_args()
    
    print("=" * 70)
    print(" " * 20 + "OmniGAT 模型訓練")
    print("=" * 70)
    
    # 檢查設備
    device = args.device
    if device == 'cuda' and not torch.cuda.is_available():
        logger.warning("CUDA 不可用，切換至 CPU")
        device = 'cpu'
    
    logger.info(f"使用設備：{device}")
    
    # 加載圖數據
    graph_data_path = Path(args.graph_data)
    if not graph_data_path.exists():
        logger.error(f"圖數據文件不存在：{graph_data_path}")
        logger.error("請先執行 Stage 3 生成圖數據（python main.py --enable-stage3 --enable-labeling）")
        return 1
    
    logger.info(f"加載圖數據：{graph_data_path}")
    pyg_data = torch.load(str(graph_data_path))
    
    # 檢查標籤
    if not hasattr(pyg_data, 'y'):
        logger.error("圖數據缺少標籤（y）")
        logger.error("請先執行 Stage 3 的標籤生成（--enable-labeling）")
        return 1
    
    logger.info(f"數據統計：")
    logger.info(f"  節點數：{pyg_data.num_nodes}")
    logger.info(f"  邊數：{pyg_data.edge_index.shape[1]}")
    logger.info(f"  特徵維度：{pyg_data.x.shape[1]}")
    logger.info(f"  標籤數：{pyg_data.y.shape[0]}")
    logger.info(f"  正樣本數：{pyg_data.y.sum().item()}")
    logger.info(f"  正樣本比例：{pyg_data.y.sum().item() / len(pyg_data.y) * 100:.2f}%")
    
    # 數據分割
    print("\n" + "─" * 70)
    print("數據分割")
    print("─" * 70)
    
    pyg_data = split_data(
        pyg_data,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        stratify=True,
        random_seed=args.random_seed
    )
    
    # 創建模型
    print("\n" + "─" * 70)
    print("模型創建")
    print("─" * 70)
    
    model_config = {
        'hidden_channels': args.hidden_dim,
        'num_heads': args.num_heads,
        'dropout': args.dropout
    }
    
    model = create_model(
        in_channels=pyg_data.x.shape[1],
        config=model_config
    )
    
    logger.info(f"模型信息：")
    for key, value in model.get_model_info().items():
        logger.info(f"  {key}: {value}")
    
    # 創建訓練器
    print("\n" + "─" * 70)
    print("訓練器初始化")
    print("─" * 70)
    
    trainer = OmniGATTrainer(
        model=model,
        data=pyg_data,
        device=device,
        lr=args.lr,
        weight_decay=args.weight_decay,
        use_focal_loss=args.use_focal_loss,
        focal_alpha=args.focal_alpha,
        focal_gamma=args.focal_gamma
    )
    
    # 開始訓練
    print("\n" + "─" * 70)
    print("開始訓練")
    print("─" * 70)
    
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    history = trainer.train(
        num_epochs=args.epochs,
        verbose=args.verbose,
        save_dir=str(output_dir)
    )
    
    # 測試集評估
    print("\n" + "─" * 70)
    print("測試集評估")
    print("─" * 70)
    
    test_metrics = trainer.evaluate(pyg_data.test_mask)
    
    logger.info("測試集性能：")
    logger.info(f"  準確率 (Accuracy):  {test_metrics['accuracy']:.4f}")
    logger.info(f"  精確率 (Precision): {test_metrics['precision']:.4f}")
    logger.info(f"  召回率 (Recall):    {test_metrics['recall']:.4f}")
    logger.info(f"  F1 分數 (F1-Score): {test_metrics['f1']:.4f}")
    logger.info(f"  AUC-ROC:            {test_metrics['auc']:.4f}")
    
    cm = test_metrics['confusion_matrix']
    print(f"\n混淆矩陣：")
    print(f"  實際負類 | 預測負類: {cm[0][0]:4d}   預測正類: {cm[0][1]:4d}")
    print(f"  實際正類 | 預測負類: {cm[1][0]:4d}   預測正類: {cm[1][1]:4d}")
    
    # 注意力權重分析
    if args.analyze_attention:
        print("\n" + "─" * 70)
        print("注意力權重分析")
        print("─" * 70)
        
        top_edges = trainer.analyze_attention_weights(top_k=15)
        
        print(f"\nTop-15 高注意力權重的邊（模型最關注的依賴關係）：")
        for i, (src, dst, score) in enumerate(top_edges, 1):
            print(f"  {i:2d}. 節點 {src:4d} → {dst:4d}  (權重: {score:.4f})")
    
    # 保存訓練報告
    import json
    report_path = output_dir / "training_report.json"
    with open(report_path, 'w') as f:
        json.dump({
            'model_config': model_config,
            'training_config': {
                'epochs': args.epochs,
                'lr': args.lr,
                'weight_decay': args.weight_decay,
                'device': device,
                'train_ratio': args.train_ratio,
                'val_ratio': args.val_ratio,
                'test_ratio': args.test_ratio
            },
            'test_metrics': {
                'accuracy': test_metrics['accuracy'],
                'precision': test_metrics['precision'],
                'recall': test_metrics['recall'],
                'f1': test_metrics['f1'],
                'auc': test_metrics['auc'],
                'confusion_matrix': test_metrics['confusion_matrix']
            },
            'history': history
        }, f, indent=2)
    
    logger.info(f"\n訓練報告已保存至：{report_path}")
    
    # 完成
    print("\n" + "=" * 70)
    print(" " * 20 + "訓練完成！")
    print("=" * 70)
    print(f"\n模型已保存至：{output_dir / 'omni_gat_best.pth'}")
    print(f"訓練報告：{report_path}")
    print(f"訓練歷史：{output_dir / 'training_history.json'}")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用戶中斷訓練")
        sys.exit(1)
    except Exception as e:
        logger.error(f"訓練失敗：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
