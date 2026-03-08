"""
OmniTrace - 主程式入口
整合階段 1 和階段 2 的功能
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 添加 src 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.stage1_parser import ClangParser, find_source_files
from src.stage2_graph import SoftwareGraph, analyze_codebase
from src.stage3_features import FeatureExtractor, to_pyg_data, preprocess_graph
from src.stage3_labeler import apply_labels, save_labels_report


def load_config(config_path: str = "config.json") -> dict:
    """載入配置文件"""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def parse_arguments():
    """解析命令行參數"""
    parser = argparse.ArgumentParser(
        description='OmniTrace - C/C++ 靜態分析與圖形化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  # 分析單個文件
  python main.py --file example.cpp
  
  # 分析整個目錄
  python main.py --dir ./src
  
  # 指定輸出目錄
  python main.py --dir ./src --output ./analysis_results
  
  # 使用自定義 libclang 路徑
  python main.py --dir ./src --libclang /path/to/libclang.dll
        """
    )
    
    # 輸入選項
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--file', '-f', help='要分析的 C/C++ 文件')
    input_group.add_argument('--dir', '-d', help='要分析的目錄（遞歸搜索）')
    input_group.add_argument('--json', '-j', help='直接分析已有的 JSON 文件（跳過解析階段）')
    
    # 配置選項
    parser.add_argument('--output', '-o', default='./output', 
                        help='輸出目錄（默認：./output）')
    parser.add_argument('--libclang', help='libclang 動態庫路徑')
    parser.add_argument('--include', '-I', action='append', 
                        help='頭文件搜索路徑（可多次指定）')
    parser.add_argument('--config', '-c', default='config.json',
                        help='配置文件路徑（默認：config.json）')
    
    # 分析選項
    parser.add_argument('--no-god-objects', action='store_true',
                        help='跳過 God Object 檢測')
    parser.add_argument('--no-cycles', action='store_true',
                        help='跳過循環依賴檢測')
    parser.add_argument('--no-coupling', action='store_true',
                        help='跳過耦合度分析')
    
    # 階段 3 選項
    parser.add_argument('--enable-stage3', action='store_true',
                        help='啟用階段 3：AI 特徵提取與 PyG 數據轉換')
    parser.add_argument('--embedding-model', default='all-MiniLM-L6-v2',
                        help='語義嵌入模型（默認：all-MiniLM-L6-v2）')
    parser.add_argument('--scaler-type', choices=['standard', 'minmax'], default='standard',
                        help='數值特徵縮放方法（默認：standard）')
    parser.add_argument('--enable-labeling', action='store_true',
                        help='啟用標籤生成（需搭配 --enable-stage3）')
    parser.add_argument('--known-bugs', default='data/known_bugs.json',
                        help='已知 Bug 映射文件路徑（默認：data/known_bugs.json）')
    
    # 階段 5 選項（GNN 模型訓練與推論）
    parser.add_argument('--enable-stage5', action='store_true',
                        help='啟用階段 5：GNN 模型訓練與推論')
    parser.add_argument('--stage5-mode', choices=['train', 'predict'], default='train',
                        help='Stage 5 模式：train（訓練）或 predict（推論）')
    parser.add_argument('--graph-data', default='output/graph_data.pt',
                        help='PyG 圖數據路徑（默認：output/graph_data.pt）')
    parser.add_argument('--model-path', default='output/models/omni_gat_best.pth',
                        help='模型保存/加載路徑（默認：output/models/omni_gat_best.pth）')
    parser.add_argument('--epochs', type=int, default=200,
                        help='訓練輪數（默認：200）')
    parser.add_argument('--hidden-dim', type=int, default=64,
                        help='隱藏層維度（默認：64）')
    parser.add_argument('--num-heads', type=int, default=4,
                        help='注意力頭數（默認：4）')
    parser.add_argument('--dropout', type=float, default=0.3,
                        help='Dropout 比例（默認：0.3）')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='學習率（默認：0.001）')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu',
                        help='計算設備（默認：cpu）')
    
    return parser.parse_args()


def main():
    """主函數"""
    args = parse_arguments()
    config = load_config(args.config)
    
    # 創建輸出目錄
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    print("="*70)
    print(" "*20 + "OmniTrace 啟動")
    print("="*70)
    
    # ========== 階段 1：源碼解析 ==========
    
    if args.json:
        # 直接加載已有的 JSON
        print(f"\n加載現有分析結果：{args.json}")
        json_path = args.json
    else:
        print("\n" + "─"*70)
        print("階段 1：C/C++ 源碼解析")
        print("─"*70)
        
        # 初始化解析器
        parser = ClangParser(libclang_path=args.libclang)
        
        # 獲取源文件列表
        if args.file:
            source_files = [args.file]
            print(f"分析文件：{args.file}")
        else:
            source_files = find_source_files(args.dir)
            print(f"分析目錄：{args.dir}")
            print(f"   找到 {len(source_files)} 個源文件")
        
        # 執行解析
        include_paths = args.include or config.get('parser', {}).get('include_paths', [])
        result = parser.analyze_project(source_files, include_paths)
        
        # 保存解析結果
        json_path = output_dir / "parsed_data.json"
        parser.export_to_json(str(json_path))
    
    # ========== 階段 2：圖形分析 ==========
    
    print("\n" + "─"*70)
    print("階段 2：依賴圖分析")
    print("─"*70)
    
    # 載入並分析
    graph = SoftwareGraph()
    graph.load_from_json(str(json_path))
    
    # 執行指定的分析
    if not args.no_god_objects:
        threshold = config.get('analysis', {}).get('god_object_threshold', 0.15)
        graph.detect_god_objects(threshold)
    
    if not args.no_cycles:
        graph.detect_circular_dependencies()
    
    if not args.no_coupling:
        graph.calculate_coupling_metrics()
    
    # ========== 階段 3：AI 特徵提取（可選）==========
    
    if args.enable_stage3:
        print("\n" + "─"*70)
        print("階段 3：AI 特徵工程與 PyG 數據轉換")
        print("─"*70)
        
        # 預處理圖形
        print("\n正在預處理圖形...")
        processed_graph = preprocess_graph(graph.graph)
        
        # 初始化特徵提取器
        print(f"\n正在初始化特徵提取器...")
        print(f"   語義嵌入模型：{args.embedding_model}")
        print(f"   特徵縮放方法：{args.scaler_type}")
        
        extractor = FeatureExtractor(
            embedding_model=args.embedding_model,
            scaler_type=args.scaler_type
        )
        
        # 轉換為 PyG Data 格式
        print(f"\n正在轉換至 PyTorch Geometric 格式...")
        pyg_data = to_pyg_data(processed_graph, extractor)
        
        # 標籤生成（可選）
        if args.enable_labeling:
            print("\n" + "─"*70)
            print("階段 3 延伸：弱監督標籤生成")
            print("─"*70)
            
            # 應用標籤
            known_bugs_path = args.known_bugs if os.path.exists(args.known_bugs) else None
            if known_bugs_path:
                print(f"使用已知 Bug 文件：{known_bugs_path}")
            else:
                print(f"未找到已知 Bug 文件：{args.known_bugs}（將跳過規則 3）")
            
            apply_labels(pyg_data, processed_graph, 
                        known_bugs_path=known_bugs_path,
                        verbose=True)
            
            # 保存標籤報告
            labels_report_path = output_dir / "labels_report.json"
            save_labels_report(pyg_data, str(labels_report_path))
            
            print(f"\n標籤已整合至 PyG 數據")
            print(f"   標籤報告已保存至：{labels_report_path}")
        
        # 保存 PyG Data
        import torch
        pyg_data_path = output_dir / "graph_data.pt"
        torch.save(pyg_data, str(pyg_data_path))
        
        print(f"\n階段 3 完成：")
        print(f"   節點數：{pyg_data.num_nodes}")
        print(f"   邊數：{pyg_data.edge_index.shape[1]}")
        print(f"   特徵維度：{pyg_data.x.shape[1]}")
        if args.enable_labeling:
            print(f"   標籤維度：{pyg_data.y.shape[0]} (已生成)")
        print(f"   PyG 數據已保存至：{pyg_data_path}")
    
    # ========== 階段 5：GNN 模型訓練與推論（可選）==========
    
    if args.enable_stage5:
        import torch
        from src.stage5_model import create_model
        from src.stage5_trainer import OmniGATTrainer, split_data
        from src.stage5_inference import BugPredictor
        
        print("\n" + "─"*70)
        print("階段 5：GNN Bug 預測模型")
        print("─"*70)
        
        # 檢查設備
        device = args.device
        if device == 'cuda' and not torch.cuda.is_available():
            print("[WARN] CUDA 不可用，切換至 CPU")
            device = 'cpu'
        
        print(f"使用設備：{device}")
        
        # 加載圖數據
        graph_data_path = Path(args.graph_data)
        if not graph_data_path.exists():
            print(f"✗ 圖數據文件不存在：{graph_data_path}")
            print(f"  請先執行 Stage 3 生成圖數據（使用 --enable-stage3 --enable-labeling）")
            return 1
        
        print(f"加載圖數據：{graph_data_path}")
        pyg_data = torch.load(str(graph_data_path))
        
        # 檢查標籤
        if not hasattr(pyg_data, 'y'):
            print("✗ 圖數據缺少標籤（y）")
            print("  請先執行 Stage 3 的標籤生成（使用 --enable-labeling）")
            return 1
        
        print(f"   節點數：{pyg_data.num_nodes}")
        print(f"   邊數：{pyg_data.edge_index.shape[1]}")
        print(f"   特徵維度：{pyg_data.x.shape[1]}")
        print(f"   標籤數：{pyg_data.y.shape[0]}")
        print(f"   正樣本數：{pyg_data.y.sum().item()}")
        
        if args.stage5_mode == 'train':
            # ========== 訓練模式 ==========
            
            print("\n" + "─"*70)
            print("模式：訓練（Train）")
            print("─"*70)
            
            # 數據分割
            print("\n正在分割數據集...")
            pyg_data = split_data(
                pyg_data,
                train_ratio=0.6,
                val_ratio=0.2,
                test_ratio=0.2,
                stratify=True,
                random_seed=42
            )
            
            # 創建模型
            print("\n正在創建 OmniGAT 模型...")
            model_config = {
                'hidden_channels': args.hidden_dim,
                'num_heads': args.num_heads,
                'dropout': args.dropout
            }
            
            model = create_model(
                in_channels=pyg_data.x.shape[1],
                config=model_config
            )
            
            print(f"   模型參數：{model.count_parameters():,}")
            
            # 創建訓練器
            print("\n正在初始化訓練器...")
            trainer = OmniGATTrainer(
                model=model,
                data=pyg_data,
                device=device,
                lr=args.lr,
                weight_decay=5e-4,
                use_focal_loss=True,
                focal_alpha=0.75,
                focal_gamma=2.0
            )
            
            # 開始訓練
            print("\n" + "─"*70)
            print("開始訓練")
            print("─"*70)
            
            models_dir = output_dir / "models"
            models_dir.mkdir(exist_ok=True, parents=True)
            
            history = trainer.train(
                num_epochs=args.epochs,
                verbose=10,
                save_dir=str(models_dir)
            )
            
            # 測試集評估
            print("\n" + "─"*70)
            print("測試集評估")
            print("─"*70)
            
            test_metrics = trainer.evaluate(pyg_data.test_mask)
            
            print(f"   準確率 (Accuracy):  {test_metrics['accuracy']:.4f}")
            print(f"   精確率 (Precision): {test_metrics['precision']:.4f}")
            print(f"   召回率 (Recall):    {test_metrics['recall']:.4f}")
            print(f"   F1 分數 (F1-Score): {test_metrics['f1']:.4f}")
            print(f"   AUC-ROC:            {test_metrics['auc']:.4f}")
            
            cm = test_metrics['confusion_matrix']
            print(f"\n   混淆矩陣：")
            print(f"      TN: {cm[0][0]:4d}   FP: {cm[0][1]:4d}")
            print(f"      FN: {cm[1][0]:4d}   TP: {cm[1][1]:4d}")
            
            # 注意力權重分析
            print("\n" + "─"*70)
            print("注意力權重分析")
            print("─"*70)
            
            top_edges = trainer.analyze_attention_weights(top_k=10)
            
            print(f"\nTop-10 高注意力權重的邊（模型最關注的依賴關係）：")
            for i, (src, dst, score) in enumerate(top_edges, 1):
                print(f"   {i:2d}. 節點 {src:4d} → {dst:4d}  (權重: {score:.4f})")
            
            # 保存訓練報告
            report_path = models_dir / "training_report.json"
            with open(report_path, 'w') as f:
                import json
                json.dump({
                    'model_config': model_config,
                    'training_config': {
                        'epochs': args.epochs,
                        'lr': args.lr,
                        'device': device
                    },
                    'test_metrics': test_metrics,
                    'top_attention_edges': [
                        {'source': src, 'target': dst, 'weight': score}
                        for src, dst, score in top_edges
                    ]
                }, f, indent=2)
            
            print(f"\n訓練報告已保存至：{report_path}")
            
        else:
            # ========== 推論模式 ==========
            
            print("\n" + "─"*70)
            print("模式：推論（Predict）")
            print("─"*70)
            
            model_path = Path(args.model_path)
            if not model_path.exists():
                print(f"✗ 模型文件不存在：{model_path}")
                print(f"  請先執行訓練模式（--stage5-mode train）")
                return 1
            
            # 加載預測器
            print(f"\n加載模型：{model_path}")
            predictor = BugPredictor(str(model_path), device=device)
            
            # 預測所有節點
            print("\n正在預測...")
            predictions = predictor.predict_all(pyg_data)
            
            print(f"   預測了 {len(predictions)} 個節點")
            
            # 獲取高風險節點
            print("\n" + "─"*70)
            print("高風險節點分析")
            print("─"*70)
            
            high_risk_nodes = predictor.get_high_risk_nodes(
                pyg_data,
                threshold=0.7,
                top_k=20
            )
            
            print(f"\nTop-20 高風險節點：")
            for i, (node_id, prob) in enumerate(high_risk_nodes, 1):
                print(f"   {i:2d}. 節點 {node_id:4d}  (風險機率: {prob:.4f})")
            
            # 導出可視化數據
            predictions_dir = output_dir / "predictions"
            predictions_dir.mkdir(exist_ok=True, parents=True)
            
            vis_export_path = predictions_dir / "visualization_data.json"
            predictor.export_for_visualization(
                pyg_data,
                str(vis_export_path),
                include_metadata=True
            )
            
            print(f"\n可視化數據已導出至：{vis_export_path}")
            
            # 合併到圖數據
            merged_graph_path = predictions_dir / "graph_with_predictions.pt"
            predictor.merge_with_graph_data(
                str(graph_data_path),
                str(merged_graph_path)
            )
            
            print(f"預測結果已合併到圖數據：{merged_graph_path}")
            
            # 分析報告
            print("\n" + "─"*70)
            print("預測分析報告")
            print("─"*70)
            
            analysis = predictor.analyze_predictions(pyg_data)
            
            print(f"\n風險分佈：")
            for risk_level, count in analysis['risk_distribution'].items():
                print(f"   {risk_level}: {count}")
            
            print(f"\n統計信息：")
            for key, value in analysis['statistics'].items():
                print(f"   {key}: {value:.4f}")
            
            # 保存分析報告
            analysis_path = predictions_dir / "prediction_analysis.json"
            with open(analysis_path, 'w') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
            
            print(f"\n分析報告已保存至：{analysis_path}")
    
    # ========== 導出結果 ==========
    
    print("\n" + "─"*70)
    print("導出分析結果")
    print("─"*70)
    
    # 保存視覺化數據
    vis_path = output_dir / "visualization.json"
    graph.export_for_visualization(str(vis_path))
    
    # 保存分析報告
    report_path = output_dir / "report.json"
    graph.export_analysis_report(str(report_path))
    
    # 打印摘要
    graph.print_summary()
    
    print("\n" + "="*70)
    print(f"分析完成！結果保存在：{output_dir.absolute()}")
    print("="*70)
    print(f"\n查看結果：")
    print(f"   - 視覺化數據：{vis_path}")
    print(f"   - 分析報告：{report_path}")
    if args.enable_stage3:
        print(f"   - PyG 圖數據：{output_dir / 'graph_data.pt'}")
        if args.enable_labeling:
            print(f"   - 標籤報告：{output_dir / 'labels_report.json'}")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用戶中斷執行")
        sys.exit(1)
    except Exception as e:
        print(f"\n錯誤：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
