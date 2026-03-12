# -*- coding: utf-8 -*-
"""
bridge.py - Python 後端新增 Auto-TB 生成方法範例

[使用說明]
請將本檔案中的 generate_auto_tb 方法複製到您現有的 src/bridge.py 中的 Bridge 類別內。
"""

from PyQt6.QtCore import pyqtSlot
import json
import subprocess
import os
from pathlib import Path


class Bridge(QObject):
    """
    [範例] 在現有的 Bridge 類別中新增以下方法
    """
    
    # ...existing signals and methods...
    
    @pyqtSlot(str, result=str)
    def generate_auto_tb(self, config_json: str) -> str:
        """
        接收前端傳來的測資設定 JSON，執行自動化 Testbench 生成與模擬
        
        工作流程：
        1. 解析前端傳來的 JSON 設定
        2. 儲存設定檔到 examples/ui_generated_config.json
        3. 呼叫 auto_tb_generator.py 生成 Verilog Testbench
        4. (可選) 自動執行 iverilog + vvp 模擬
        5. 回傳生成結果給前端
        
        參數:
            config_json (str): 前端組裝的完整設定 JSON 字串，格式如下：
                {
                    "top_module": "ATE",
                    "clock": {"signal_name": "clk", "period_ns": 10, "initial_value": 0},
                    "reset": {"signal_name": "reset", "active_high": true, "duration_ns": 20},
                    "stimulus_bindings": [
                        {"input_name": "pix_data", "width": 8, "data_file": "tb1.map", "radix": "hex"}
                    ],
                    "outputs": [{"name": "max_min", "width": 8}],
                    "simulation": {"test_cycles": 4096, "vcd_output": "auto_sim.vcd"}
                }
            
        回傳:
            str: JSON 格式的結果字串
                成功: {"success": true, "testbench_path": "...", "config_path": "..."}
                失敗: {"success": false, "error": "錯誤訊息"}
        """
        try:
            # ========== 步驟 1: 解析前端傳來的設定 ==========
            config_data = json.loads(config_json)
            top_module = config_data.get('top_module', 'unknown')
            print(f"[Bridge] [Auto-TB] Received config for module: {top_module}")
            
            # ========== 步驟 2: 儲存設定檔到檔案系統 ==========
            # 確保 examples 目錄存在
            examples_dir = Path('examples')
            examples_dir.mkdir(exist_ok=True)
            
            # 設定檔路徑
            config_path = examples_dir / 'ui_generated_config.json'
            
            # 寫入設定檔 (使用 UTF-8 編碼，保留中文註解)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            print(f"[Bridge] [Auto-TB] Config saved to: {config_path}")
            
            # ========== 步驟 3: 呼叫 auto_tb_generator.py 生成 Testbench ==========
            tb_output_path = examples_dir / f"{top_module}_auto_tb.v"
            
            # 構建命令列參數
            cmd_generate = [
                'python',                        # Python 直譯器
                'src/auto_tb_generator.py',      # TB 生成器腳本
                '-c', str(config_path),          # 設定檔路徑
                '-o', str(tb_output_path)        # 輸出 Testbench 路徑
            ]
            
            print(f"[Bridge] [Auto-TB] Executing: {' '.join(cmd_generate)}")
            
            # 執行命令並捕捉輸出
            result_gen = subprocess.run(
                cmd_generate,
                capture_output=True,    # 捕捉 stdout 和 stderr
                text=True,              # 以文字模式處理輸出
                encoding='utf-8',       # 使用 UTF-8 編碼
                cwd=os.getcwd()         # 在當前工作目錄執行
            )
            
            # 檢查執行結果
            if result_gen.returncode != 0:
                # 生成失敗，回傳錯誤訊息
                error_msg = f"Testbench 生成失敗 (Exit Code {result_gen.returncode}): {result_gen.stderr}"
                print(f"[Bridge] [Auto-TB] ERROR: {error_msg}")
                return json.dumps({
                    "success": False,
                    "error": error_msg
                }, ensure_ascii=False)
            
            print(f"[Bridge] [Auto-TB] Testbench generated successfully: {tb_output_path}")
            print(f"[Bridge] [Auto-TB] Generator output:\n{result_gen.stdout}")
            
            # ========== 步驟 4 (可選): 自動執行 iverilog 編譯與 vvp 模擬 ==========
            # 取得 VCD 輸出路徑
            vcd_output = config_data.get('simulation', {}).get('vcd_output', f'{top_module}_auto_sim.vcd')
            vcd_output_path = examples_dir / vcd_output
            
            # 是否啟用自動模擬 (預設關閉，避免執行時間過長)
            auto_simulate = config_data.get('auto_simulate', False)
            
            if auto_simulate:
                print(f"[Bridge] [Auto-TB] Starting simulation...")
                
                # 編譯 Testbench (iverilog)
                compiled_output = examples_dir / 'sim.out'
                cmd_compile = [
                    'iverilog',
                    '-o', str(compiled_output),
                    str(tb_output_path)
                ]
                
                result_compile = subprocess.run(cmd_compile, capture_output=True, text=True, encoding='utf-8')
                if result_compile.returncode != 0:
                    error_msg = f"iverilog 編譯失敗: {result_compile.stderr}"
                    print(f"[Bridge] [Auto-TB] ERROR: {error_msg}")
                    return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
                
                print(f"[Bridge] [Auto-TB] Compilation successful")
                
                # 執行模擬 (vvp)
                cmd_simulate = ['vvp', str(compiled_output)]
                result_simulate = subprocess.run(cmd_simulate, capture_output=True, text=True, encoding='utf-8')
                
                if result_simulate.returncode != 0:
                    error_msg = f"vvp 模擬失敗: {result_simulate.stderr}"
                    print(f"[Bridge] [Auto-TB] ERROR: {error_msg}")
                    return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
                
                print(f"[Bridge] [Auto-TB] Simulation complete, VCD: {vcd_output_path}")
            
            # ========== 步驟 5: 回傳成功結果 ==========
            response = {
                "success": True,
                "testbench_path": str(tb_output_path),
                "config_path": str(config_path),
                "vcd_path": str(vcd_output_path) if auto_simulate else None,
                "message": f"Testbench 生成成功！檔案已儲存至 {tb_output_path}"
            }
            
            return json.dumps(response, ensure_ascii=False)
            
        except json.JSONDecodeError as e:
            # JSON 解析錯誤
            error_msg = f"JSON 解析錯誤: {str(e)}"
            print(f"[Bridge] [Auto-TB] ERROR: {error_msg}")
            return json.dumps({
                "success": False,
                "error": error_msg
            }, ensure_ascii=False)
            
        except FileNotFoundError as e:
            # 檔案或命令不存在
            error_msg = f"檔案或命令未找到: {str(e)}"
            print(f"[Bridge] [Auto-TB] ERROR: {error_msg}")
            return json.dumps({
                "success": False,
                "error": error_msg
            }, ensure_ascii=False)
            
        except Exception as e:
            # 其他未預期的錯誤
            error_msg = f"執行錯誤: {str(e)}"
            print(f"[Bridge] [Auto-TB] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "error": error_msg
            }, ensure_ascii=False)


# ========== 使用範例 (單元測試) ==========
if __name__ == "__main__":
    """
    單元測試：模擬前端傳送的 JSON 資料
    """
    # 模擬前端設定資料
    test_config = {
        "top_module": "ATE",
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
        "stimulus_bindings": [
            {
                "input_name": "pix_data",
                "width": 8,
                "data_file": "tb1.map",
                "radix": "hex",
                "description": "8-bit 輸入"
            },
            {
                "input_name": "type",
                "width": 1,
                "data_file": "tb2.map",
                "radix": "bin",
                "description": "1-bit 輸入"
            }
        ],
        "outputs": [
            {"name": "max_min", "width": 8, "description": "8-bit 輸出"},
            {"name": "threshold", "width": 8, "description": "8-bit 輸出"}
        ],
        "simulation": {
            "test_cycles": 4096,
            "vcd_output": "ATE_auto_sim.vcd",
            "display_interval": 512
        },
        "comments": {
            "purpose": "Auto-generated Testbench Config from UI",
            "date": "2026-03-10"
        }
    }
    
    # 序列化為 JSON 字串
    config_json = json.dumps(test_config, indent=2, ensure_ascii=False)
    
    print("[Test] Simulating frontend call to generate_auto_tb()...")
    print(f"[Test] Config JSON:\n{config_json}\n")
    
    # 模擬呼叫 (需要在實際的 Bridge 實例中執行)
    # bridge_instance = Bridge()
    # result = bridge_instance.generate_auto_tb(config_json)
    # print(f"[Test] Result:\n{result}")
