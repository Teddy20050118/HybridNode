"""
硬體模擬器 - 第三階段 (動態模擬)
使用 Icarus Verilog 自動編譯與執行 Testbench，解析 VCD 波形檔

此模組負責：
1. 自動化編譯 Verilog 原始碼與 Testbench (iverilog)
2. 執行模擬並產生 VCD 波形檔 (vvp)
3. 原生解析 VCD 檔案格式（無需外部套件）
4. 實作狀態保持機制，補齊每個時間點的完整狀態
5. 輸出為 React 可直接渲染的 JSON 格式
"""

import os
import sys
import json
import re
import subprocess
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from collections import defaultdict


class VCDParser:
    """
    VCD (Value Change Dump) 波形檔解析器
    原生實作，不依賴外部套件，支援狀態保持機制
    
    重要：VCD 中同一個 symbol 可能對應多個 scope（因為 Verilog 的 wire 連接），
    例如 symbol '#' 同時是 sample_tb.clk、sample_tb.uut.clk、sample_tb.uut.F1.clk。
    解析器會為每個唯一的 (scope, name) 組合建立獨立的訊號記錄，
    並輸出以階層路徑為 key 的 signals 字典。
    """
    
    def __init__(self):
        """初始化 VCD 解析器"""
        # symbol → [{ name, type, width, scope, full_path }, ...]
        # 一個 symbol 可能對應多個階層路徑
        self.symbol_to_entries = defaultdict(list)
        # 所有唯一的 full_path 列表（用於 signal_data 的 key）
        self.all_paths = []
        self.time_steps = []  # 所有時間點
        self.signal_data = defaultdict(list)  # key = full_path，每個訊號的數值序列
        self.current_state = {}  # symbol → 當前值（用於狀態保持）
        self.current_time = 0  # 當前時間點
        self.target_scope = None  # 目標模組範圍
        
    def parse_file(self, vcd_path: str, target_module: Optional[str] = None) -> Dict[str, Any]:
        """
        解析 VCD 檔案
        
        Args:
            vcd_path: VCD 檔案路徑
            target_module: 目標模組名稱（若為 None 則解析所有變數）
            
        Returns:
            包含時間步與訊號資料的字典
        """
        print(f"\n開始解析 VCD 檔案：{vcd_path}")
        
        if not os.path.isfile(vcd_path):
            print(f"錯誤：VCD 檔案不存在 - {vcd_path}")
            return {"error": f"VCD 檔案不存在：{vcd_path}"}
        
        self.target_scope = target_module
        
        try:
            with open(vcd_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            print(f"讀取到 {len(lines)} 行資料")
            
            # 第一階段：解析 Header（建立符號映射）
            self._parse_header(lines)
            
            # 第二階段：解析 Dump（提取波形資料）
            self._parse_dump(lines)
            
            # 第三階段：整理輸出格式
            result = self._build_result()
            
            print(f"解析完成：{len(self.time_steps)} 個時間點，{len(self.signal_data)} 個訊號")
            
            return result
            
        except Exception as e:
            error_msg = f"解析 VCD 檔案時發生異常：{str(e)}"
            print(f"錯誤：{error_msg}")
            import traceback
            traceback.print_exc()
            return {"error": error_msg}
    
    def _parse_header(self, lines: List[str]):
        """
        解析 VCD Header 區塊
        建立 VCD 符號到變數名稱的映射字典（支援階層路徑）
        
        一個 VCD symbol 在不同 scope 中可能代表同一條 wire（如 clk 被連接到多個子模組），
        此時它們共用同一個 VCD symbol。我們為每個 (scope, name) 組合建立獨立記錄。
        
        Args:
            lines: VCD 檔案的所有行
        """
        print("\n解析 Header 區塊...")
        
        in_scope = False
        current_scope = []
        var_count = 0
        
        for line in lines:
            line = line.strip()
            
            # 遇到 $enddefinitions 表示 Header 結束
            if line.startswith("$enddefinitions"):
                break
            
            # 進入 Scope
            if line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope_name = parts[2]
                    current_scope.append(scope_name)
                    
                    # 如果指定了目標模組，檢查是否進入目標範圍
                    if self.target_scope and scope_name == self.target_scope:
                        in_scope = True
                    elif self.target_scope is None:
                        in_scope = True
            
            # 離開 Scope
            elif line.startswith("$upscope"):
                if current_scope:
                    leaving_scope = current_scope.pop()
                    if self.target_scope and leaving_scope == self.target_scope:
                        in_scope = False
            
            # 解析變數定義
            elif line.startswith("$var") and in_scope:
                # 格式：$var wire 1 ! clk $end
                # 格式：$var reg 8 " data_in [7:0] $end
                parts = line.split()
                
                if len(parts) >= 5:
                    var_type = parts[1]  # wire, reg, integer 等
                    width = parts[2]  # 位元寬度
                    symbol = parts[3]  # VCD 符號（ASCII 字元）
                    var_name = parts[4]  # 變數名稱
                    
                    # 移除可能的位元範圍標記 [7:0]
                    var_name = re.sub(r'\[.*?\]', '', var_name)
                    
                    # 建立階層路徑：scope1.scope2.var_name
                    scope_path = '.'.join(current_scope)
                    full_path = f"{scope_path}.{var_name}"
                    
                    # 檢查此 full_path 是否已被記錄（避免重複）
                    existing_paths = [e["full_path"] for e in self.symbol_to_entries[symbol]]
                    if full_path not in existing_paths:
                        entry = {
                            "name": var_name,
                            "type": var_type,
                            "width": int(width) if width.isdigit() else 1,
                            "scope": scope_path,
                            "full_path": full_path
                        }
                        self.symbol_to_entries[symbol].append(entry)
                        self.all_paths.append(full_path)
                    
                    # 初始化狀態為 "x" (未知)
                    self.current_state[symbol] = "x"
                    var_count += 1
        
        print(f"找到 {var_count} 個變數定義，{len(self.all_paths)} 個唯一階層路徑")
        # 顯示前幾個
        for path in self.all_paths[:20]:
            print(f"  {path}")
        if len(self.all_paths) > 20:
            print(f"  ... 還有 {len(self.all_paths) - 20} 個")
    
    def _parse_dump(self, lines: List[str]):
        """
        解析 VCD Dump 區塊
        提取時間標記與數值變化，實作狀態保持機制
        
        Args:
            lines: VCD 檔案的所有行
        """
        print("\n解析 Dump 區塊...")
        
        in_dump = False
        time_point_count = 0
        
        for line in lines:
            line = line.strip()
            
            # 跳過空行與註解
            if not line or line.startswith("$comment"):
                continue
            
            # 開始進入 Dump 區塊
            if line.startswith("$dumpvars") or line.startswith("$dumpon"):
                in_dump = True
                continue
            
            # Dump 區塊結束標記
            if line.startswith("$end") and in_dump:
                continue
            
            if in_dump:
                # 時間標記（例如 #0, #10, #20）
                if line.startswith("#"):
                    # 儲存上一個時間點的狀態
                    if time_point_count > 0 or self.current_time > 0:
                        self._save_current_state()
                    
                    # 更新時間
                    self.current_time = int(line[1:])
                    self.time_steps.append(self.current_time)
                    time_point_count += 1
                
                # 數值變化（例如 0!, 1", b1010 #）
                else:
                    self._parse_value_change(line)
        
        # 儲存最後一個時間點的狀態
        if time_point_count > 0:
            self._save_current_state()
        
        print(f"解析到 {time_point_count} 個時間點")
    
    def _parse_value_change(self, line: str):
        """
        解析數值變化行
        
        VCD 格式範例：
        - 單一位元：0! (符號 ! 的值變為 0)
        - 單一位元：1" (符號 " 的值變為 1)
        - 多位元：b1010 # (符號 # 的值變為 b1010)
        - 多位元：b10xx01 $ (符號 $ 的值變為 b10xx01)
        - 實數：r3.14 %
        
        Args:
            line: VCD 數值變化行
        """
        line = line.strip()
        
        # 處理單一位元變化（值在前，符號在後）
        # 格式：0!, 1", x#
        if len(line) >= 2 and line[0] in "01xzXZ":
            value = line[0]
            symbol = line[1:]
            
            if symbol in self.symbol_to_entries:
                self.current_state[symbol] = value
        
        # 處理多位元變化（以 'b' 或 'B' 開頭）
        # 格式：b1010 #, b10xx01 $
        elif line.startswith("b") or line.startswith("B"):
            parts = line.split()
            if len(parts) >= 2:
                value = parts[0][1:]  # 移除開頭的 'b'
                symbol = parts[1]
                
                if symbol in self.symbol_to_entries:
                    # 補齊前導零（根據變數寬度，取第一個 entry 的寬度）
                    width = self.symbol_to_entries[symbol][0]["width"]
                    value = self._normalize_binary_value(value, width)
                    self.current_state[symbol] = value
        
        # 處理實數變化（以 'r' 開頭）
        elif line.startswith("r"):
            parts = line.split()
            if len(parts) >= 2:
                value = parts[0][1:]  # 移除開頭的 'r'
                symbol = parts[1]
                
                if symbol in self.symbol_to_entries:
                    self.current_state[symbol] = value
    
    def _normalize_binary_value(self, value: str, width: int) -> str:
        """
        正規化二進位值（補齊前導零或處理 x/z）
        
        Args:
            value: 二進位值字串（可能包含 x, z）
            width: 目標位元寬度
            
        Returns:
            正規化後的二進位字串
        """
        # 移除空白
        value = value.strip()
        
        # 如果包含 x 或 z，保持原樣
        if 'x' in value.lower() or 'z' in value.lower():
            return value
        
        # 補齊前導零
        if len(value) < width:
            value = '0' * (width - len(value)) + value
        
        return value
    
    def _save_current_state(self):
        """
        儲存當前時間點的所有訊號狀態
        實作狀態保持機制：未變化的訊號保持前一個狀態
        
        每個 VCD symbol 可能對應多個階層路徑（相同的物理線路），
        它們共享同一個值。我們為每個 full_path 都記錄一份。
        """
        for symbol, entries in self.symbol_to_entries.items():
            current_value = self.current_state.get(symbol, "x")
            for entry in entries:
                full_path = entry["full_path"]
                self.signal_data[full_path].append(current_value)
    
    def _build_result(self) -> Dict[str, Any]:
        """
        建立最終輸出結果
        
        輸出格式：
        - signals: 以階層路徑為 key（如 "sample_tb.uut.F1.pix_data"）
        - flat_signals: 以短名稱為 key（如 "pix_data"），僅保留頂層 testbench 的 scope
          用於向後相容（頂層節點可直接用短名稱查詢）
        - scope_map: 從 "instance.signal" 到 full_path 的映射，
          用於前端展開子模組時查找正確的訊號
        
        Returns:
            包含 time_steps, signals, flat_signals, scope_map, metadata 的字典
        """
        # 轉換 defaultdict 為普通 dict
        signals = {name: values for name, values in self.signal_data.items()}
        
        # 建立 flat_signals：以短名稱為 key，取最淺層 scope 的訊號
        # 規則：按 scope 層數排序，最淺的優先
        flat_signals = {}
        for full_path, values in signals.items():
            parts = full_path.rsplit('.', 1)
            short_name = parts[-1] if len(parts) > 1 else full_path
            
            if short_name not in flat_signals:
                flat_signals[short_name] = values
            else:
                # 比較 scope 深度，選擇最淺的
                existing_depth = None
                for existing_path, existing_vals in signals.items():
                    if existing_vals is flat_signals[short_name]:
                        existing_depth = existing_path.count('.')
                        break
                current_depth = full_path.count('.')
                if existing_depth is not None and current_depth < existing_depth:
                    flat_signals[short_name] = values
        
        # 建立 scope_map：instance_name.signal_name → full_path
        # 例如：F1.pix_data → sample_tb.uut.F1.pix_data
        # 例如：th0.f0.a → sample_tb.uut.th0.f0.a
        scope_map = {}
        for full_path in signals.keys():
            # 從 full_path 中提取各層級的相對路徑
            # sample_tb.uut.F1.pix_data → F1.pix_data, uut.F1.pix_data, ...
            parts = full_path.split('.')
            for i in range(1, len(parts)):
                relative_path = '.'.join(parts[i:])
                if relative_path not in scope_map:
                    scope_map[relative_path] = full_path
        
        return {
            "time_steps": self.time_steps,
            "signals": flat_signals,          # 向後相容：短名稱 key
            "hierarchical_signals": signals,  # 完整階層路徑 key
            "scope_map": scope_map,           # 相對路徑 → 完整路徑 映射
            "metadata": {
                "total_steps": len(self.time_steps),
                "total_signals": len(signals),
                "total_flat_signals": len(flat_signals),
                "signal_names": list(signals.keys()),
                "flat_signal_names": list(flat_signals.keys())
            }
        }


class HardwareSimulator:
    """
    硬體模擬器主類別
    自動化編譯、執行模擬、解析 VCD
    """
    
    def __init__(self, work_dir: str = "simulation"):
        """
        初始化模擬器
        
        Args:
            work_dir: 工作目錄（存放編譯產物與 VCD 檔案）
        """
        self.work_dir = work_dir
        self.compiled_output = None
        self.vcd_output = None
        
        # 建立工作目錄
        if not os.path.exists(work_dir):
            os.makedirs(work_dir)
            print(f"已建立工作目錄：{work_dir}")
    
    def _create_wrapper_if_needed(self, source_files: List[str]) -> Optional[str]:
        """
        檢查 testbench 是否包含 include 指令，若無則自動生成 wrapper
        
        Args:
            source_files: 原始檔案列表（通常是 [design.v, testbench.v]）
            
        Returns:
            wrapper 檔案路徑，若不需要則回傳 None
        """
        if len(source_files) < 2:
            return None
        
        # 假設最後一個檔案是 testbench
        testbench_file = source_files[-1]
        design_files = source_files[:-1]
        
        try:
            # 讀取 testbench 內容（使用 UTF-8 並忽略錯誤）
            with open(testbench_file, 'r', encoding='utf-8', errors='ignore') as f:
                testbench_content = f.read()
            
            # 檢查是否已包含 include 指令
            has_include = '`include' in testbench_content
            
            if has_include:
                print("Testbench 已包含 include 指令，無需生成 wrapper")
                return None
            
            print("Testbench 未包含 include 指令，將自動生成 wrapper 檔案")
            
            # 生成 wrapper 內容
            wrapper_content = "// 自動生成的封裝檔案\n"
            wrapper_content += "// 此檔案由 HybridNode 自動產生，用於解決模組引用問題\n\n"
            
            # 包含所有設計檔案
            for design_file in design_files:
                # 轉換為相對路徑（避免路徑問題）
                rel_path = os.path.relpath(design_file, self.work_dir)
                # 統一使用正斜線（Verilog 標準）
                rel_path = rel_path.replace('\\', '/')
                wrapper_content += f'`include "{rel_path}"\n'
            
            # 包含 testbench
            rel_testbench = os.path.relpath(testbench_file, self.work_dir)
            rel_testbench = rel_testbench.replace('\\', '/')
            wrapper_content += f'`include "{rel_testbench}"\n'
            
            # 儲存 wrapper 檔案
            wrapper_path = os.path.join(self.work_dir, "wrapper_auto_generated.v")
            with open(wrapper_path, 'w', encoding='utf-8') as f:
                f.write(wrapper_content)
            
            print(f"Wrapper 檔案已產生：{wrapper_path}")
            return wrapper_path
            
        except Exception as e:
            print(f"警告：生成 wrapper 時發生錯誤 - {str(e)}")
            return None
    
    def check_tools(self) -> Tuple[bool, str]:
        """
        檢查 Icarus Verilog 工具是否已安裝
        
        Returns:
            (是否可用, 錯誤訊息)
        """
        print("\n檢查模擬工具...")
        
        try:
            # 檢查 iverilog（使用 -V 大寫 V 顯示版本）
            result = subprocess.run(
                ["iverilog", "-V"],
                capture_output=True,
                text=True,
                timeout=5, encoding='utf-8', errors='ignore'
            )
            
            if result.returncode == 0:
                # 提取版本資訊（stdout 或 stderr 都可能包含版本）
                version_output = result.stdout if result.stdout else result.stderr
                version_line = version_output.split('\n')[0] if version_output else "未知版本"
                print(f"找到 Icarus Verilog：{version_line}")
                return True, ""
            else:
                return False, "iverilog 指令執行失敗"
                
        except FileNotFoundError:
            error_msg = "找不到 iverilog 指令，請先安裝 Icarus Verilog"
            print(f"錯誤：{error_msg}")
            print("安裝方式：")
            print("  Windows: 下載安裝檔 http://bleyer.org/icarus/")
            print("  Linux: sudo apt-get install iverilog")
            print("  macOS: brew install icarus-verilog")
            return False, error_msg
            
        except subprocess.TimeoutExpired:
            return False, "iverilog 指令執行逾時"
            
        except Exception as e:
            return False, f"檢查工具時發生異常：{str(e)}"
    
    def compile(self, source_files: List[str], output_name: str = "sim.out") -> Tuple[bool, str]:
        """
        編譯 Verilog 原始碼
        
        Args:
            source_files: Verilog 檔案列表（包含主程式與 testbench）
            output_name: 編譯輸出檔名
            
        Returns:
            (編譯成功, 訊息或錯誤)
        """
        print("\n" + "=" * 60)
        print("開始編譯 Verilog 原始碼")
        print("=" * 60)
        
        # 檢查所有檔案是否存在
        for source_file in source_files:
            if not os.path.isfile(source_file):
                error_msg = f"原始檔案不存在：{source_file}"
                print(f"錯誤：{error_msg}")
                return False, error_msg
        
        # 智慧型檔案排序：Design 檔案在前，Testbench 在後
        design_files = []
        testbench_files = []
        
        for source_file in source_files:
            # 讀取檔案內容判斷類型（使用 UTF-8 並忽略錯誤）
            try:
                with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                
                # 判斷是否為 testbench（包含 $dumpfile 或檔名含 tb）
                if '$dumpfile' in content or '$dumpvars' in content or 'tb' in os.path.basename(source_file).lower():
                    testbench_files.append(source_file)
                else:
                    design_files.append(source_file)
            except:
                # 無法判斷，假設為設計檔案
                design_files.append(source_file)
        
        # 重新排序：設計檔案在前
        sorted_files = design_files + testbench_files
        print(f"檔案排序：")
        print(f"  設計檔案：{design_files}")
        print(f"  測試檔案：{testbench_files}")
        
        # 檢查是否需要自動生成包含指令
        wrapper_file = None
        if len(sorted_files) >= 2:
            wrapper_file = self._create_wrapper_if_needed(sorted_files)
            if wrapper_file:
                print(f"已產生封裝檔案：{wrapper_file}")
                sorted_files = [wrapper_file]
        
        # 編譯輸出路徑（標準化路徑分隔符號）
        self.compiled_output = os.path.normpath(os.path.join(self.work_dir, output_name))
        
        # 取得所有原始檔案的目錄（用於 -y 搜尋路徑）
        search_dirs = set()
        for source_file in source_files:  # 使用原始檔案列表
            dir_path = os.path.dirname(os.path.abspath(source_file))
            if dir_path:
                search_dirs.add(dir_path)
        
        # 加入當前目錄與工作目錄
        search_dirs.add(os.getcwd())
        search_dirs.add(os.path.abspath(self.work_dir))
        
        # 建立 iverilog 指令（強化搜尋路徑）
        cmd = ["iverilog", "-o", self.compiled_output]
        
        # 加入 Include 搜尋路徑 (-I)
        for search_dir in search_dirs:
            cmd.extend(["-I", search_dir])
        
        # 加入模組搜尋路徑 (-y)
        for search_dir in search_dirs:
            cmd.extend(["-y", search_dir])
        
        # 加入原始檔案
        cmd.extend(sorted_files)
        
        print(f"編譯指令：{' '.join(cmd)}")
        print(f"搜尋路徑：{list(search_dirs)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30, encoding='utf-8', errors='ignore'
            )
            
            # 輸出編譯訊息
            if result.stdout:
                print("\n編譯輸出：")
                print(result.stdout)
            
            if result.stderr:
                print("\n編譯警告/錯誤：")
                print(result.stderr)
            
            if result.returncode == 0:
                print(f"\n編譯成功：{self.compiled_output}")
                return True, "編譯成功"
            else:
                error_msg = f"編譯失敗（退出碼 {result.returncode}）"
                if result.stderr:
                    error_msg += f"\n{result.stderr}"
                print(f"\n錯誤：{error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "編譯逾時（超過 30 秒）"
            print(f"錯誤：{error_msg}")
            return False, error_msg
            
        except Exception as e:
            error_msg = f"編譯時發生異常：{str(e)}"
            print(f"錯誤：{error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg
    
    def simulate(self, vcd_name: str = "dump.vcd") -> Tuple[bool, str]:
        """
        執行模擬
        
        Args:
            vcd_name: VCD 輸出檔名
            
        Returns:
            (模擬成功, 訊息或錯誤)
        """
        print("\n" + "=" * 60)
        print("開始執行模擬")
        print("=" * 60)
        
        if not self.compiled_output or not os.path.isfile(self.compiled_output):
            error_msg = "找不到編譯輸出檔，請先執行編譯"
            print(f"錯誤：{error_msg}")
            return False, error_msg
        
        # VCD 輸出路徑
        self.vcd_output = os.path.join(self.work_dir, vcd_name)
        
        compiled_filename = os.path.basename(self.compiled_output)
        cmd = ["vvp", compiled_filename]
        
        print(f"模擬指令：{' '.join(cmd)}")
        
        try:
            # 切換到工作目錄（確保 VCD 檔案產生在正確位置）
            original_dir = os.getcwd()
            os.chdir(self.work_dir)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60, encoding='utf-8', errors='ignore'
            )
            
            # 切回原目錄
            os.chdir(original_dir)
            
            # 輸出模擬訊息
            if result.stdout:
                print("\n模擬輸出：")
                print(result.stdout)
            
            if result.stderr:
                print("\n模擬警告/錯誤：")
                print(result.stderr)
            
            if result.returncode == 0:
                # 檢查 VCD 檔案是否產生
                if os.path.isfile(self.vcd_output):
                    vcd_size = os.path.getsize(self.vcd_output)
                    print(f"\n模擬成功：VCD 檔案已產生（大小：{vcd_size} bytes）")
                    return True, "模擬成功"
                else:
                    error_msg = f"模擬完成，但找不到 VCD 檔案：{self.vcd_output}"
                    print(f"警告：{error_msg}")
                    print("請確認 testbench 中是否包含 $dumpfile 與 $dumpvars 指令")
                    return False, error_msg
            else:
                error_msg = f"模擬失敗（退出碼 {result.returncode}）"
                if result.stderr:
                    error_msg += f"\n{result.stderr}"
                print(f"\n錯誤：{error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            os.chdir(original_dir)
            error_msg = "模擬逾時（超過 60 秒）"
            print(f"錯誤：{error_msg}")
            return False, error_msg
            
        except Exception as e:
            os.chdir(original_dir)
            error_msg = f"模擬時發生異常：{str(e)}"
            print(f"錯誤：{error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg
    
    def parse_vcd(self, target_module: Optional[str] = None) -> Dict[str, Any]:
        """
        解析 VCD 波形檔
        
        Args:
            target_module: 目標模組名稱
            
        Returns:
            包含波形資料的字典
        """
        print("\n" + "=" * 60)
        print("開始解析 VCD 波形檔")
        print("=" * 60)
        
        if not self.vcd_output or not os.path.isfile(self.vcd_output):
            error_msg = f"找不到 VCD 檔案：{self.vcd_output}"
            print(f"錯誤：{error_msg}")
            return {"error": error_msg}
        
        parser = VCDParser()
        result = parser.parse_file(self.vcd_output, target_module)
        
        return result
    
    def run_full_simulation(
        self,
        source_files: List[str],
        target_module: Optional[str] = None,
        output_json: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        執行完整的模擬流程
        
        Args:
            source_files: Verilog 檔案列表
            target_module: 目標模組名稱
            output_json: 輸出 JSON 檔案路徑
            
        Returns:
            模擬結果字典
        """
        print("\n" + "=" * 60)
        print("開始完整模擬流程")
        print("=" * 60)
        
        # 檢查工具
        tools_ok, error_msg = self.check_tools()
        if not tools_ok:
            return {"error": error_msg}
        
        # 編譯
        compile_ok, compile_msg = self.compile(source_files)
        if not compile_ok:
            return {"error": compile_msg}
        
        # 模擬
        simulate_ok, simulate_msg = self.simulate()
        if not simulate_ok:
            return {"error": simulate_msg}
        
        # 解析 VCD
        result = self.parse_vcd(target_module)
        
        if "error" in result:
            return result
        
        # 儲存 JSON（如果指定）
        if output_json:
            try:
                # 確保輸出目錄存在
                output_dir = os.path.dirname(output_json)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)
                    print(f"已建立輸出目錄：{output_dir}")
                
                with open(output_json, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                
                print(f"\n結果已儲存至：{output_json}")
                
            except Exception as e:
                print(f"\n警告：無法儲存 JSON 檔案 - {str(e)}")
        
        print("\n" + "=" * 60)
        print("模擬流程完成")
        print("=" * 60)
        
        return result


def main():
    """
    主函式：提供命令列介面
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="硬體模擬器 - 自動編譯、執行模擬、解析 VCD 波形檔"
    )
    parser.add_argument(
        "source",
        help="Verilog 原始檔案路徑"
    )
    parser.add_argument(
        "testbench",
        help="Testbench 檔案路徑"
    )
    parser.add_argument(
        "-o", "--output",
        help="輸出 JSON 檔案路徑",
        default="output/simulation_data.json"
    )
    parser.add_argument(
        "-m", "--module",
        help="目標模組名稱（只解析特定模組的訊號）",
        default=None
    )
    parser.add_argument(
        "-w", "--workdir",
        help="工作目錄（存放編譯產物與 VCD）",
        default="simulation"
    )
    
    args = parser.parse_args()
    
    # 建立模擬器
    simulator = HardwareSimulator(work_dir=args.workdir)
    
    # 執行完整模擬
    result = simulator.run_full_simulation(
        source_files=[args.source, args.testbench],
        target_module=args.module,
        output_json=args.output
    )
    
    # 檢查結果
    if "error" in result:
        print(f"\n模擬失敗：{result['error']}")
        sys.exit(1)
    else:
        meta = result.get('metadata', {})
        print(f"\n模擬成功！")
        print(f"  階層訊號數量：{meta.get('total_signals', '?')}")
        print(f"  扁平訊號數量：{meta.get('total_flat_signals', '?')}")
        print(f"  時間點數量：{meta.get('total_steps', '?')}")
        flat_names = meta.get('flat_signal_names', meta.get('signal_names', []))
        print(f"  扁平訊號名稱：{', '.join(flat_names)}")
        sys.exit(0)


if __name__ == "__main__":
    main()
