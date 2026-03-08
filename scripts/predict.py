"""
Stage 5 推論腳本
使用訓練好的 OmniGAT 模型進行 Bug 預測
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
from src.stage5_inference import BugPredictor

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """解析命令行參數"""
    parser = argparse.ArgumentParser(
        description='OmniGAT 模型推論腳本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  # 基本推論
  python scripts/predict.py
  
  # 自定義模型和數據路徑
  python scripts/predict.py --model output/models/omni_gat_best.pth --graph-data output/graph_data.pt
  
  # 調整風險閾值
  python scripts/predict.py --risk-threshold 0.8
  
  # 使用 GPU
  python scripts/predict.py --device cuda
        """
    )
    
    # 輸入與輸出
    parser.add_argument('--model', '-m', default='output/models/omni_gat_best.pth',
                        help='訓練好的模型路徑（默認：output/models/omni_gat_best.pth）')
    parser.add_argument('--graph-data', default='output/graph_data.pt',
                        help='PyG 圖數據路徑（默認：output/graph_data.pt）')
    parser.add_argument('--output', '-o', default='output/predictions',
                        help='預測結果保存目錄（默認：output/predictions）')
    
    # 推論配置
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu',
                        help='計算設備（默認：cpu）')
    parser.add_argument('--risk-threshold', type=float, default=0.7,
                        help='高風險閾值（默認：0.7）')
    parser.add_argument('--top-k', type=int, default=20,
                        help='顯示前 K 個高風險節點（默認：20）')
    
    # 輸出選項
    parser.add_argument('--export-visualization', action='store_true', default=True,
                        help='導出可視化數據（默認：True）')
    parser.add_argument('--merge-graph', action='store_true',
                        help='將預測結果合併到圖數據')
    parser.add_argument('--analyze', action='store_true', default=True,
                        help='生成詳細分析報告（默認：True）')
    
    return parser.parse_args()


def main():
    """主函數"""
    args = parse_args()
    
    print("=" * 70)
    print(" " * 20 + "OmniGAT 模型推論")
    print("=" * 70)
    
    # 檢查設備
    device = args.device
    if device == 'cuda' and not torch.cuda.is_available():
        logger.warning("CUDA 不可用，切換至 CPU")
        device = 'cpu'
    
    logger.info(f"使用設備：{device}")
    
    # 檢查模型文件
    model_path = Path(args.model)
    if not model_path.exists():
        logger.error(f"模型文件不存在：{model_path}")
        logger.error("請先執行訓練腳本：python scripts/train_model.py")
        return 1
    
    # 檢查圖數據
    graph_data_path = Path(args.graph_data)
    if not graph_data_path.exists():
        logger.error(f"圖數據文件不存在：{graph_data_path}")
        logger.error("請先執行 Stage 3 生成圖數據")
        return 1
    
    # 創建輸出目錄
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # 加載預測器
    print("\n" + "─" * 70)
    print("加載模型")
    print("─" * 70)
    
    predictor = BugPredictor(str(model_path), device=device)
    
    # 加載圖數據
    logger.info(f"加載圖數據：{graph_data_path}")
    pyg_data = torch.load(str(graph_data_path))
    
    logger.info(f"數據統計：")
    logger.info(f"  節點數：{pyg_data.num_nodes}")
    logger.info(f"  邊數：{pyg_data.edge_index.shape[1]}")
    logger.info(f"  特徵維度：{pyg_data.x.shape[1]}")
    
    # 執行預測
    print("\n" + "─" * 70)
    print("執行預測")
    print("─" * 70)
    
    logger.info("正在預測所有節點...")
    predictions = predictor.predict_all(pyg_data)
    
    logger.info(f"預測完成，共 {len(predictions)} 個節點")
    
    # 高風險節點分析
    print("\n" + "─" * 70)
    print("高風險節點分析")
    print("─" * 70)
    
    high_risk_nodes = predictor.get_high_risk_nodes(
        pyg_data,
        threshold=args.risk_threshold,
        top_k=args.top_k
    )
    
    print(f"\nTop-{args.top_k} 高風險節點（閾值: {args.risk_threshold}）：")
    print(f"{'排名':<6} {'節點ID':<10} {'風險機率':<12}")
    print("─" * 30)
    
    for i, (node_id, prob) in enumerate(high_risk_nodes, 1):
        print(f"{i:<6} {node_id:<10} {prob:.6f}")
    
    # 導出可視化數據
    if args.export_visualization:
        print("\n" + "─" * 70)
        print("導出可視化數據")
        print("─" * 70)
        
        vis_export_path = output_dir / "visualization_data.json"
        predictor.export_for_visualization(
            pyg_data,
            str(vis_export_path),
            include_metadata=True
        )
        
        logger.info(f"可視化數據已導出至：{vis_export_path}")
    
    # 合併到圖數據
    if args.merge_graph:
        print("\n" + "─" * 70)
        print("合併預測結果")
        print("─" * 70)
        
        merged_graph_path = output_dir / "graph_with_predictions.pt"
        predictor.merge_with_graph_data(
            str(graph_data_path),
            str(merged_graph_path)
        )
        
        logger.info(f"預測結果已合併到圖數據：{merged_graph_path}")
    
    # 詳細分析
    if args.analyze:
        print("\n" + "─" * 70)
        print("預測分析報告")
        print("─" * 70)
        
        analysis = predictor.analyze_predictions(pyg_data)
        
        # 風險分佈
        print("\n風險分佈：")
        for risk_level, count in analysis['risk_distribution'].items():
            percentage = count / analysis['total_nodes'] * 100
            print(f"  {risk_level:<25} {count:>5} 個 ({percentage:>5.2f}%)")
        
        # 統計信息
        print("\n統計信息：")
        stats = analysis['statistics']
        print(f"  平均風險機率：{stats['mean']:.4f}")
        print(f"  標準差：      {stats['std']:.4f}")
        print(f"  最小值：      {stats['min']:.4f}")
        print(f"  最大值：      {stats['max']:.4f}")
        print(f"  中位數：      {stats['median']:.4f}")
        print(f"  95 百分位：   {stats['percentile_95']:.4f}")
        print(f"  99 百分位：   {stats['percentile_99']:.4f}")
        
        # 如果有真實標籤，顯示評估指標
        if 'evaluation' in analysis:
            print("\n評估指標（與真實標籤比較）：")
            eval_metrics = analysis['evaluation']
            print(f"  準確率 (Accuracy):  {eval_metrics['accuracy']:.4f}")
            print(f"  精確率 (Precision): {eval_metrics['precision']:.4f}")
            print(f"  召回率 (Recall):    {eval_metrics['recall']:.4f}")
            print(f"  F1 分數:            {eval_metrics['f1_score']:.4f}")
            if 'auc_roc' in eval_metrics:
                print(f"  AUC-ROC:            {eval_metrics['auc_roc']:.4f}")
            
            cm = eval_metrics['confusion_matrix']
            print(f"\n  混淆矩陣：")
            print(f"    真陰性 (TN): {cm['true_negatives']:>5}")
            print(f"    假陽性 (FP): {cm['false_positives']:>5}")
            print(f"    假陰性 (FN): {cm['false_negatives']:>5}")
            print(f"    真陽性 (TP): {cm['true_positives']:>5}")
        
        # 保存分析報告
        import json
        analysis_path = output_dir / "prediction_analysis.json"
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n分析報告已保存至：{analysis_path}")
    
    # 保存預測結果（CSV 格式）
    csv_path = output_dir / "predictions.csv"
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write("NodeID,Risk Probability\n")
        for node_id, prob in predictions.items():
            f.write(f"{node_id},{prob:.6f}\n")
    
    logger.info(f"預測結果已保存至：{csv_path}")
    
    # 完成
    print("\n" + "=" * 70)
    print(" " * 20 + "推論完成！")
    print("=" * 70)
    print(f"\n輸出文件：")
    print(f"  預測結果 (CSV):      {csv_path}")
    if args.export_visualization:
        print(f"  可視化數據 (JSON):   {output_dir / 'visualization_data.json'}")
    if args.merge_graph:
        print(f"  合併圖數據 (.pt):    {output_dir / 'graph_with_predictions.pt'}")
    if args.analyze:
        print(f"  分析報告 (JSON):     {output_dir / 'prediction_analysis.json'}")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用戶中斷推論")
        sys.exit(1)
    except Exception as e:
        logger.error(f"推論失敗：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
