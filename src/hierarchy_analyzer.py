"""
階層式 Verilog 解析器擴充模組
提供模組階層分析、頂層模組判斷、輸入端口提取等功能

此模組擴充 hw_stage1_parser.py 的功能，新增：
1. find_top_module(): 自動判斷頂層模組
2. build_module_hierarchy(): 建立模組階層樹
3. extract_module_inputs(): 提取每個模組的輸入端口資訊
4. extract_module_instances(): 提取模組例現化關係

用於支援前端的階層式視覺化與自動 Testbench 生成
"""

import json
from typing import Dict, List, Any, Set, Tuple, Optional
from collections import defaultdict


class HierarchyAnalyzer:
    """
    模組階層分析器
    分析 Verilog 設計中的模組階層關係
    """
    
    def __init__(self, parsed_data: Dict[str, Any]):
        """
        初始化階層分析器
        
        Args:
            parsed_data: hw_stage1_parser.py 的輸出結果
        """
        self.nodes = parsed_data.get('nodes', [])
        self.edges = parsed_data.get('edges', [])
        
        # 建立模組相關資料結構
        self.module_definitions = defaultdict(lambda: {
            'inputs': [],
            'outputs': [],
            'wires': [],
            'regs': [],
            'nodes': [],
            'edges': []
        })
        
        self.module_instances = defaultdict(list)  # 模組例現化關係
        self.all_modules = set()  # 所有定義的模組
        self.instantiated_modules = set()  # 被例現化過的模組
        
        # 初始化時進行分析
        self._analyze_modules()
    
    def _analyze_modules(self):
        """分析模組定義與節點歸屬"""
        print("\n開始分析模組階層...")
        
        # 第一步：收集所有模組名稱與其節點
        for node in self.nodes:
            module_name = node.get('module')
            if not module_name:
                continue
            
            self.all_modules.add(module_name)
            
            node_type = node.get('type')
            node_id = node.get('id')
            
            # 分類儲存節點
            if node_type == 'input':
                self.module_definitions[module_name]['inputs'].append(node)
            elif node_type == 'output':
                self.module_definitions[module_name]['outputs'].append(node)
            elif node_type == 'wire':
                self.module_definitions[module_name]['wires'].append(node)
            elif node_type == 'reg':
                self.module_definitions[module_name]['regs'].append(node)
            
            self.module_definitions[module_name]['nodes'].append(node)
        
        # 第二步：收集每個模組的連線
        for edge in self.edges:
            module_name = edge.get('module')
            if module_name:
                self.module_definitions[module_name]['edges'].append(edge)
        
        print(f"  發現 {len(self.all_modules)} 個模組定義")
    
    def find_top_module(self) -> Optional[str]:
        """
        判斷頂層模組
        頂層模組的特徵：未被其他模組例現化
        
        Returns:
            頂層模組名稱，若無法判斷則返回 None
        """
        # TODO: 實際專案中需要解析 ModuleInstance 節點
        # 目前簡化版本：假設第一個模組為頂層模組
        
        # 方法 1: 若只有一個模組，則為頂層
        if len(self.all_modules) == 1:
            top_module = list(self.all_modules)[0]
            print(f"\n頂層模組判斷：僅有一個模組 - {top_module}")
            return top_module
        
        # 方法 2: 尋找未被例現化的模組
        # 注意：此處需要 AST 中的 InstanceList 資訊，目前版本簡化處理
        non_instantiated = self.all_modules - self.instantiated_modules
        
        if len(non_instantiated) == 1:
            top_module = list(non_instantiated)[0]
            print(f"\n頂層模組判斷：唯一未被例現化的模組 - {top_module}")
            return top_module
        elif len(non_instantiated) > 1:
            # 多個候選，選擇第一個
            top_module = sorted(non_instantiated)[0]
            print(f"\n頂層模組判斷：多個候選，選擇第一個 - {top_module}")
            print(f"  候選模組：{sorted(non_instantiated)}")
            return top_module
        
        # 方法 3: 預設使用第一個模組
        if self.all_modules:
            top_module = sorted(self.all_modules)[0]
            print(f"\n頂層模組判斷：預設使用第一個模組 - {top_module}")
            return top_module
        
        print("\n警告：無法判斷頂層模組")
        return None
    
    def extract_module_inputs(self, module_name: str) -> List[Dict[str, Any]]:
        """
        提取指定模組的所有輸入端口資訊
        
        Args:
            module_name: 模組名稱
            
        Returns:
            輸入端口資訊列表
        """
        inputs = []
        
        for node in self.module_definitions[module_name]['inputs']:
            input_info = {
                'name': node.get('id'),
                'width': node.get('width', 1),
                'msb': node.get('msb'),
                'lsb': node.get('lsb'),
                'type': 'input'
            }
            inputs.append(input_info)
        
        return inputs
    
    def extract_module_outputs(self, module_name: str) -> List[Dict[str, Any]]:
        """
        提取指定模組的所有輸出端口資訊
        
        Args:
            module_name: 模組名稱
            
        Returns:
            輸出端口資訊列表
        """
        outputs = []
        
        for node in self.module_definitions[module_name]['outputs']:
            output_info = {
                'name': node.get('id'),
                'width': node.get('width', 1),
                'msb': node.get('msb'),
                'lsb': node.get('lsb'),
                'type': 'output'
            }
            outputs.append(output_info)
        
        return outputs
    
    def build_module_hierarchy(self, top_module: str) -> Dict[str, Any]:
        """
        建立模組階層樹
        
        Args:
            top_module: 頂層模組名稱
            
        Returns:
            階層樹結構
        """
        # TODO: 實際專案中需要解析 InstanceList 來建立完整階層
        # 目前簡化版本：只返回基本資訊
        
        hierarchy = {
            'top_module': top_module,
            'all_modules': sorted(self.all_modules),
            'module_tree': {
                top_module: {
                    'children': [],  # 子模組列表
                    'depth': 0,
                    'instances': []  # 例現化資訊
                }
            }
        }
        
        print(f"\n模組階層樹：")
        print(f"  頂層模組：{top_module}")
        print(f"  所有模組：{hierarchy['all_modules']}")
        
        return hierarchy
    
    def generate_enhanced_output(self) -> Dict[str, Any]:
        """
        產生增強版的輸出格式
        包含原始節點/連線 + 階層資訊 + 輸入/輸出端口
        
        Returns:
            增強版輸出資料
        """
        print("\n產生增強版輸出...")
        
        # 判斷頂層模組
        top_module = self.find_top_module()
        
        # 建立階層樹
        hierarchy = self.build_module_hierarchy(top_module) if top_module else {}
        
        # 提取每個模組的端口資訊
        module_ports = {}
        for module_name in self.all_modules:
            module_ports[module_name] = {
                'inputs': self.extract_module_inputs(module_name),
                'outputs': self.extract_module_outputs(module_name),
                'nodes_count': len(self.module_definitions[module_name]['nodes']),
                'edges_count': len(self.module_definitions[module_name]['edges'])
            }
        
        # 組合完整輸出
        enhanced_output = {
            'nodes': self.nodes,
            'edges': self.edges,
            'hierarchy': hierarchy,
            'module_definitions': dict(self.module_definitions),
            'module_ports': module_ports
        }
        
        # 統計資訊
        print(f"\n增強版輸出統計：")
        print(f"  總節點數：{len(self.nodes)}")
        print(f"  總連線數：{len(self.edges)}")
        print(f"  模組數量：{len(self.all_modules)}")
        if top_module:
            print(f"  頂層模組：{top_module}")
            inputs = module_ports.get(top_module, {}).get('inputs', [])
            outputs = module_ports.get(top_module, {}).get('outputs', [])
            print(f"    - 輸入端口：{len(inputs)} 個")
            print(f"    - 輸出端口：{len(outputs)} 個")
        
        return enhanced_output


def enhance_parsed_data(parsed_data_path: str, output_path: str = None) -> Dict[str, Any]:
    """
    增強解析資料，加入階層資訊
    
    Args:
        parsed_data_path: hw_stage1_parser.py 輸出的 JSON 檔案路徑
        output_path: 增強版輸出路徑（若為 None 則不寫入檔案）
        
    Returns:
        增強版資料
    """
    print(f"\n載入解析資料：{parsed_data_path}")
    
    # 載入原始解析資料
    with open(parsed_data_path, 'r', encoding='utf-8') as f:
        parsed_data = json.load(f)
    
    # 處理可能的陣列格式（批次解析結果）
    if isinstance(parsed_data, list) and len(parsed_data) > 0:
        parsed_data = parsed_data[0]  # 取第一個檔案的結果
    
    # 建立階層分析器
    analyzer = HierarchyAnalyzer(parsed_data)
    
    # 產生增強版輸出
    enhanced_data = analyzer.generate_enhanced_output()
    
    # 寫入檔案
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enhanced_data, f, indent=2, ensure_ascii=False)
        print(f"\n增強版資料已儲存至：{output_path}")
    
    return enhanced_data


def generate_stimulus_config_template(
    parsed_data_path: str, 
    output_path: str = "stimulus_config_template.json"
) -> Dict[str, Any]:
    """
    根據解析結果自動產生測資設定檔範本
    
    Args:
        parsed_data_path: hw_stage1_parser.py 輸出的 JSON 檔案路徑
        output_path: 設定檔範本輸出路徑
        
    Returns:
        設定檔範本
    """
    print(f"\n根據解析結果產生測資設定檔範本...")
    
    # 載入並分析
    with open(parsed_data_path, 'r', encoding='utf-8') as f:
        parsed_data = json.load(f)
    
    if isinstance(parsed_data, list) and len(parsed_data) > 0:
        parsed_data = parsed_data[0]
    
    analyzer = HierarchyAnalyzer(parsed_data)
    top_module = analyzer.find_top_module()
    
    if not top_module:
        print("錯誤：無法判斷頂層模組")
        return {}
    
    # 提取輸入與輸出
    inputs = analyzer.extract_module_inputs(top_module)
    outputs = analyzer.extract_module_outputs(top_module)
    
    # 建立設定檔範本
    template = {
        "top_module": top_module,
        "clock": {
            "signal_name": "clk",
            "period_ns": 10,
            "initial_value": 0
        },
        "reset": {
            "signal_name": "reset",
            "active_high": True,
            "duration_ns": 20
        },
        "stimulus_bindings": [],
        "outputs": [],
        "simulation": {
            "test_cycles": 1000,
            "vcd_output": f"{top_module}_sim.vcd",
            "display_interval": 100
        }
    }
    
    # 為每個輸入建立綁定範本
    for inp in inputs:
        name = inp['name']
        width = inp['width']
        
        # 跳過時脈與重置訊號
        if name in ['clk', 'reset']:
            continue
        
        binding = {
            "input_name": name,
            "width": width,
            "data_file": f"{name}_data.dat",
            "radix": "hex" if width > 1 else "bin",
            "description": f"{width}-bit 輸入訊號"
        }
        template['stimulus_bindings'].append(binding)
    
    # 為每個輸出建立資訊
    for out in outputs:
        output_info = {
            "name": out['name'],
            "width": out['width'],
            "description": f"{out['width']}-bit 輸出訊號"
        }
        template['outputs'].append(output_info)
    
    # 寫入檔案
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=4, ensure_ascii=False)
    
    print(f"\n測資設定檔範本已產生：{output_path}")
    print(f"  頂層模組：{top_module}")
    print(f"  輸入訊號：{len(template['stimulus_bindings'])} 個")
    print(f"  輸出訊號：{len(template['outputs'])} 個")
    print(f"\n請編輯此檔案，設定正確的測資檔案路徑，然後使用：")
    print(f"  python src/auto_tb_generator.py -c {output_path} -o auto_tb.v")
    
    return template


def main():
    """命令列介面"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='HybridNode 階層式 Verilog 解析器擴充工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'parsed_json',
        help='hw_stage1_parser.py 輸出的 JSON 檔案路徑'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='增強版輸出檔案路徑'
    )
    
    parser.add_argument(
        '--gen-stimulus-template',
        action='store_true',
        help='產生測資設定檔範本'
    )
    
    parser.add_argument(
        '--stimulus-output',
        default='stimulus_config_template.json',
        help='測資設定檔範本輸出路徑'
    )
    
    args = parser.parse_args()
    
    # 增強解析資料
    enhanced_data = enhance_parsed_data(
        args.parsed_json,
        args.output
    )
    
    # 產生測資設定檔範本
    if args.gen_stimulus_template:
        generate_stimulus_config_template(
            args.parsed_json,
            args.stimulus_output
        )


if __name__ == '__main__':
    main()
