"""
自動化 Testbench 生成器
根據使用者設定的測資綁定關係，自動產生完整的 Verilog Testbench

此模組負責：
1. 解析測資綁定設定檔 (stimulus_config.json)
2. 自動生成時脈訊號 (Clock Generator)
3. 自動生成重置訊號 (Reset Logic)
4. 根據輸入端口寬度與測資檔案產生 $readmemb/$readmemh 邏輯
5. 自動例現化頂層模組並連接所有訊號
6. 生成 VCD 輸出設定

使用情境：
- 使用者只提供設計檔 (.v) 與測資檔 (.dat/.map)
- 無需手寫 Testbench
- 透過 JSON 設定檔綁定輸入訊號與測資檔案
"""

import os
import json
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path


class AutoTestbenchGenerator:
    """
    自動化 Testbench 生成器
    根據設定檔產生完整的 Verilog Testbench 程式碼
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化生成器
        
        Args:
            config_path: 設定檔路徑 (stimulus_config.json)
        """
        self.config = {}
        self.module_name = ""
        self.inputs = []
        self.outputs = []
        self.tb_name = "auto_generated_tb"
        
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)
    
    def load_config(self, config_path: str) -> bool:
        """
        載入測資綁定設定檔
        
        Args:
            config_path: JSON 設定檔路徑
            
        Returns:
            載入是否成功
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            print(f"成功載入設定檔：{config_path}")
            
            # 提取關鍵資訊
            self.module_name = self.config.get('top_module', 'top')
            
            return True
            
        except Exception as e:
            print(f"錯誤：無法載入設定檔 - {e}")
            return False
    
    def generate_testbench(self, output_path: str = "auto_generated_tb.v") -> bool:
        """
        產生完整的 Testbench 檔案
        
        Args:
            output_path: 輸出檔案路徑
            
        Returns:
            生成是否成功
        """
        if not self.config:
            print("錯誤：尚未載入設定檔")
            return False
        
        print(f"\n開始產生 Testbench：{output_path}")
        
        # 組合所有程式碼區塊
        code_sections = [
            self._generate_header(),
            self._generate_signal_declarations(),
            self._generate_memory_declarations(),
            self._generate_clock(),
            self._generate_module_instantiation(),
            self._generate_stimulus_block(),
            self._generate_footer()
        ]
        
        full_code = "\n".join(code_sections)
        
        # 寫入檔案
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_code)
            
            print(f"成功產生 Testbench：{output_path}")
            print(f"  - 模組名稱：{self.module_name}")
            print(f"  - 輸入訊號數：{len(self.config.get('stimulus_bindings', []))}")
            print(f"  - 測試週期數：{self.config.get('simulation', {}).get('test_cycles', 1000)}")
            
            return True
            
        except Exception as e:
            print(f"錯誤：無法寫入 Testbench 檔案 - {e}")
            return False
    
    def _generate_header(self) -> str:
        """產生 Testbench 檔頭"""
        clock_period = self.config.get('clock', {}).get('period_ns', 10)
        timescale = f"1ns / {int(clock_period / 10)}ps"
        
        return f"""// 自動產生的 Testbench
// 產生時間：由 HybridNode AutoTestbenchGenerator 自動生成
// 頂層模組：{self.module_name}

`timescale {timescale}

module {self.tb_name};
"""
    
    def _generate_signal_declarations(self) -> str:
        """產生訊號宣告 (reg 與 wire)"""
        lines = ["    // 訊號宣告"]
        
        # 時脈訊號
        clock_name = self.config.get('clock', {}).get('signal_name', 'clk')
        lines.append(f"    reg {clock_name};")
        
        # 重置訊號
        if 'reset' in self.config:
            reset_name = self.config['reset'].get('signal_name', 'reset')
            lines.append(f"    reg {reset_name};")
        
        # 輸入訊號 (reg)
        for binding in self.config.get('stimulus_bindings', []):
            input_name = binding['input_name']
            width = binding.get('width', 1)
            
            if width > 1:
                lines.append(f"    reg [{width-1}:0] {input_name};")
            else:
                lines.append(f"    reg {input_name};")
        
        lines.append("")
        
        # 輸出訊號 (wire)
        for output in self.config.get('outputs', []):
            output_name = output['name']
            width = output.get('width', 1)
            
            if width > 1:
                lines.append(f"    wire [{width-1}:0] {output_name};")
            else:
                lines.append(f"    wire {output_name};")
        
        return "\n".join(lines)
    
    def _generate_memory_declarations(self) -> str:
        """產生測資記憶體陣列宣告"""
        lines = ["\n    // 測資記憶體"]
        
        test_cycles = self.config.get('simulation', {}).get('test_cycles', 1000)
        
        for binding in self.config.get('stimulus_bindings', []):
            input_name = binding['input_name']
            width = binding.get('width', 1)
            mem_name = f"{input_name}_mem"
            
            if width > 1:
                lines.append(f"    reg [{width-1}:0] {mem_name} [0:{test_cycles-1}];")
            else:
                lines.append(f"    reg {mem_name} [0:{test_cycles-1}];")
        
        lines.append("    integer i;  // 迴圈計數器")
        
        return "\n".join(lines)
    
    def _generate_clock(self) -> str:
        """產生時脈訊號生成邏輯"""
        clock_name = self.config.get('clock', {}).get('signal_name', 'clk')
        period_ns = self.config.get('clock', {}).get('period_ns', 10)
        half_period = period_ns / 2
        
        return f"""
    // 時脈產生器
    initial begin
        {clock_name} = 1'b0;
        forever #{int(half_period)} {clock_name} = ~{clock_name};  // 週期 {period_ns} ns
    end
"""
    
    def _generate_module_instantiation(self) -> str:
        """產生頂層模組例現化程式碼"""
        lines = [f"\n    // 頂層模組例現化"]
        lines.append(f"    {self.module_name} uut (")
        
        # 收集所有端口
        ports = []
        
        # 時脈
        clock_name = self.config.get('clock', {}).get('signal_name', 'clk')
        ports.append(f"        .{clock_name}({clock_name})")
        
        # 重置
        if 'reset' in self.config:
            reset_name = self.config['reset'].get('signal_name', 'reset')
            ports.append(f"        .{reset_name}({reset_name})")
        
        # 輸入訊號
        for binding in self.config.get('stimulus_bindings', []):
            input_name = binding['input_name']
            ports.append(f"        .{input_name}({input_name})")
        
        # 輸出訊號
        for output in self.config.get('outputs', []):
            output_name = output['name']
            ports.append(f"        .{output_name}({output_name})")
        
        lines.append(",\n".join(ports))
        lines.append("    );")
        
        return "\n".join(lines)
    
    def _generate_stimulus_block(self) -> str:
        """產生測資載入與餵入邏輯"""
        lines = ["\n    // 測資載入與模擬控制"]
        lines.append("    initial begin")
        
        # VCD 輸出設定
        vcd_file = self.config.get('simulation', {}).get('vcd_output', 'auto_sim.vcd')
        lines.append(f"        $dumpfile(\"{vcd_file}\");")
        lines.append(f"        $dumpvars(0, {self.tb_name});")
        lines.append("")
        
        # 載入測資
        lines.append("        // 載入測資檔案")
        for binding in self.config.get('stimulus_bindings', []):
            input_name = binding['input_name']
            data_file = binding['data_file']
            radix = binding.get('radix', 'hex')
            mem_name = f"{input_name}_mem"
            
            if radix == 'hex':
                lines.append(f'        $readmemh("{data_file}", {mem_name});')
            elif radix == 'bin':
                lines.append(f'        $readmemb("{data_file}", {mem_name});')
            else:
                lines.append(f'        $readmemh("{data_file}", {mem_name});  // 預設十六進位')
        
        lines.append("")
        
        # 重置邏輯
        if 'reset' in self.config:
            reset_name = self.config['reset'].get('signal_name', 'reset')
            reset_duration = self.config['reset'].get('duration_ns', 20)
            active_high = self.config['reset'].get('active_high', True)
            active_level = '1\'b1' if active_high else '1\'b0'
            inactive_level = '1\'b0' if active_high else '1\'b1'
            
            lines.append("        // 重置序列")
            lines.append(f"        {reset_name} = {active_level};")
            lines.append(f"        #{reset_duration};")
            lines.append(f"        {reset_name} = {inactive_level};")
            lines.append("        #10;")
            lines.append("")
        
        # 餵入測資
        test_cycles = self.config.get('simulation', {}).get('test_cycles', 1000)
        clock_name = self.config.get('clock', {}).get('signal_name', 'clk')
        
        lines.append("        // 餵入測資")
        lines.append(f"        for (i = 0; i < {test_cycles}; i = i + 1) begin")
        lines.append(f"            @(posedge {clock_name});")
        
        for binding in self.config.get('stimulus_bindings', []):
            input_name = binding['input_name']
            mem_name = f"{input_name}_mem"
            lines.append(f"            {input_name} = {mem_name}[i];")
        
        # 顯示進度
        lines.append("")
        lines.append("            // 顯示進度")
        lines.append("            if (i % 512 == 0) begin")
        lines.append(f'                $display("進度：%0d / {test_cycles} 筆資料已送出 (%0t)", i, $time);')
        lines.append("            end")
        lines.append("        end")
        lines.append("")
        
        # 穩定等待
        lines.append("        // 等待穩定")
        lines.append("        #100;")
        lines.append("")
        
        # 結束模擬
        lines.append("        // 模擬完成")
        lines.append(f'        $display("模擬完成：共 {test_cycles} 筆資料 (%0t)", $time);')
        lines.append("        $finish;")
        lines.append("    end")
        
        return "\n".join(lines)
    
    def _generate_footer(self) -> str:
        """產生 Testbench 結尾"""
        return "\nendmodule\n"


def main():
    """主程式：命令列介面"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='HybridNode 自動化 Testbench 生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  python auto_tb_generator.py -c stimulus_config.json -o auto_tb.v
  python auto_tb_generator.py --config examples/ate_config.json --output testbench/ate_tb.v

設定檔格式範例 (stimulus_config.json)：
{
    "top_module": "ATE",
    "clock": {
        "signal_name": "clk",
        "period_ns": 10
    },
    "reset": {
        "signal_name": "reset",
        "active_high": true,
        "duration_ns": 20
    },
    "stimulus_bindings": [
        {
            "input_name": "pix_data",
            "width": 8,
            "data_file": "tb1.map",
            "radix": "hex"
        }
    ],
    "outputs": [
        {"name": "bin", "width": 1},
        {"name": "threshold", "width": 8}
    ],
    "simulation": {
        "test_cycles": 4096,
        "vcd_output": "auto_sim.vcd"
    }
}
        """
    )
    
    parser.add_argument(
        '-c', '--config',
        required=True,
        help='測資綁定設定檔路徑 (JSON 格式)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='auto_generated_tb.v',
        help='輸出 Testbench 檔案路徑 (預設: auto_generated_tb.v)'
    )
    
    args = parser.parse_args()
    
    # 檢查設定檔是否存在
    if not os.path.exists(args.config):
        print(f"錯誤：設定檔不存在 - {args.config}")
        print(f"請確認檔案路徑是否正確")
        sys.exit(1)
    
    # 產生 Testbench
    generator = AutoTestbenchGenerator(args.config)
    
    if generator.generate_testbench(args.output):
        print(f"\n成功！")
        print(f"Testbench 已產生：{args.output}")
        print(f"\n下一步：")
        print(f"  1. 使用 iverilog 編譯：")
        print(f"     iverilog -o simulation.out design.v {args.output}")
        print(f"  2. 執行模擬：")
        print(f"     vvp simulation.out")
        print(f"  3. 查看波形：")
        vcd_file = generator.config.get('simulation', {}).get('vcd_output', 'auto_sim.vcd')
        print(f"     gtkwave {vcd_file}")
    else:
        print(f"\n失敗：無法產生 Testbench")
        sys.exit(1)


if __name__ == '__main__':
    main()
