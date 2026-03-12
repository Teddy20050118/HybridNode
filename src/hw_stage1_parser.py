"""
Verilog 硬體描述語言解析器 - 第一階段
使用 PyVerilog 進行 AST 解析，提取硬體節點與連線資訊

此模組負責將 Verilog 原始碼解析為抽象語法樹，並提取：
1. 硬體節點：Wire, Reg, Input, Output, Inout（含位元寬度資訊）
2. 連線與賦值：Continuous Assignment, Blocking/Non-blocking Assignment
3. Always 區塊的敏感列表與邏輯類型（Sequential/Combinational）

輸出格式將用於後續建立 NetworkX 圖形，以進行硬體設計風險偵測
"""

import os
import sys
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

try:
    from pyverilog.vparser.parser import parse
    from pyverilog.vparser.ast import (
        Node,
        Source, Description, ModuleDef,
        Decl, Input, Output, Inout, Reg, Wire, Integer,
        Width, Identifier, IntConst,
        Assign, Always, SensList, Sens,
        Block, BlockingSubstitution, NonblockingSubstitution,
        IfStatement, CaseStatement, ForStatement, WhileStatement,
        Rvalue, Lvalue, Pointer, Partselect,
        UnaryOperator, Operator, Cond,
        Concat, Repeat
    )
except ImportError as e:
    print(f"錯誤：匯入 PyVerilog 模組失敗！詳細原因：{e}")
    print("安裝指令：pip install pyverilog")
    sys.exit(1)


class NodeVisitor:
    """
    手動實作的 AST 節點訪問器基底類別
    模擬 Python 內建的 ast.NodeVisitor 行為，用來遞迴遍歷 PyVerilog 的語法樹
    避免從 pyverilog.vparser.ast 匯入 NodeVisitor 可能造成的相容性問題
    """
    
    def visit(self, node):
        """
        訪問節點的主要方法
        
        Args:
            node: AST 節點
            
        Returns:
            訪問結果
        """
        if node is None:
            return None
        
        # 動態尋找對應的 visit_XXX 方法（例如 visit_ModuleDef）
        method_name = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)
    
    def generic_visit(self, node):
        """
        通用訪問方法，當沒有特定的 visit_XXX 方法時呼叫
        預設遞迴遍歷所有子節點
        
        Args:
            node: AST 節點
        """
        # 遍歷節點的所有子節點
        if hasattr(node, 'children') and callable(node.children):
            for child in node.children():
                self.visit(child)

            
class VerilogASTVisitor(NodeVisitor):
    """
    Verilog AST 訪問器
    使用 Visitor Pattern 遍歷 AST 節點，提取硬體元件與連線資訊
    """
    
    def __init__(self):
        self.nodes = []
        self.edges = []
        self.current_module = None
        self.current_always_context = None
        
    def visit_ModuleDef(self, node):
        if node.name:
            self.current_module = node.name
            print(f"正在解析模組：{self.current_module}")
        self.generic_visit(node)
        
    # 明確攔截所有硬體變數宣告，解決 0 節點問題
    def visit_Input(self, node):
        self._add_node(node, "input")
        self.generic_visit(node)

    def visit_Output(self, node):
        self._add_node(node, "output")
        self.generic_visit(node)

    def visit_Inout(self, node):
        self._add_node(node, "inout")
        self.generic_visit(node)

    def visit_Wire(self, node):
        self._add_node(node, "wire")
        self.generic_visit(node)

    def visit_Reg(self, node):
        self._add_node(node, "reg")
        self.generic_visit(node)

    def _add_node(self, node, node_type):
        node_id = getattr(node, 'name', None)
        if not node_id:
            return
            
        width_info = {"width": 1, "msb": None, "lsb": None}
        if hasattr(node, 'width') and node.width:
            width_info = self._extract_width(node.width)
            
        self.nodes.append({
            "id": node_id,
            "type": node_type,
            "module": self.current_module,
            "width": width_info["width"],
            "msb": width_info["msb"],
            "lsb": width_info["lsb"]
        })
    
    def _extract_width(self, width_node) -> Dict:
        msb = None
        lsb = None
        width = 1
        try:
            if isinstance(width_node, Width):
                if width_node.msb:
                    msb = self._extract_constant_value(width_node.msb)
                if width_node.lsb:
                    lsb = self._extract_constant_value(width_node.lsb)
                if msb is not None and lsb is not None:
                    try:
                        msb_val = int(msb) if isinstance(msb, str) else msb
                        lsb_val = int(lsb) if isinstance(lsb, str) else lsb
                        width = abs(msb_val - lsb_val) + 1
                    except (ValueError, TypeError):
                        width = 1
        except Exception as e:
            print(f"警告：提取位元寬度時發生錯誤 - {str(e)}")
        return {"msb": msb, "lsb": lsb, "width": width}
    
    def _extract_constant_value(self, node) -> Optional[str]:
        if isinstance(node, IntConst):
            return node.value
        elif isinstance(node, Identifier):
            return node.name
        elif hasattr(node, 'value'):
            return str(node.value)
        else:
            return str(node)
    
    def visit_Assign(self, node):
        try:
            lhs_vars = self._extract_variables(node.left)
            rhs_vars = self._extract_variables(node.right)
            for rhs_var in rhs_vars:
                for lhs_var in lhs_vars:
                    edge = {
                        "from": rhs_var,
                        "to": lhs_var,
                        "assign_type": "continuous",
                        "logic_type": "combinational",
                        "module": self.current_module
                    }
                    self.edges.append(edge)
        except Exception as e:
            print(f"警告：解析 Assign 節點時發生錯誤 - {str(e)}")
        self.generic_visit(node)
    
    def visit_Always(self, node):
        try:
            # 修正屬性名稱為 sens_list
            sens_list = getattr(node, 'sens_list', None)
            logic_type, sensitivity_signals = self._analyze_sensitivity_list(sens_list)
            
            self.current_always_context = {
                "logic_type": logic_type,
                "sensitivity": sensitivity_signals
            }
            
            print(f"  發現 Always 區塊：{logic_type} 邏輯，敏感訊號：{sensitivity_signals}")
            
            if node.statement:
                self.visit(node.statement)
        except Exception as e:
            print(f"警告：解析 Always 區塊時發生錯誤 - {str(e)}")
        finally:
            self.current_always_context = None
    
    def _analyze_sensitivity_list(self, sens_list) -> Tuple[str, List[str]]:
        logic_type = "combinational"
        signals = []
        if not sens_list:
            return logic_type, signals
        try:
            if isinstance(sens_list, SensList):
                for sens in sens_list.list:
                    if isinstance(sens, Sens):
                        if sens.type and sens.type in ['posedge', 'negedge']:
                            logic_type = "sequential"
                        if sens.sig:
                            sig_name = self._extract_signal_name(sens.sig)
                            if sig_name:
                                signals.append(sig_name)
        except Exception as e:
            print(f"警告：分析敏感列表時發生錯誤 - {str(e)}")
        return logic_type, signals
    
    def _extract_signal_name(self, node) -> Optional[str]:
        if isinstance(node, Identifier):
            return node.name
        elif hasattr(node, 'name'):
            return node.name
        else:
            return None
    
    def visit_BlockingSubstitution(self, node):
        self._process_assignment(node, "blocking")
        self.generic_visit(node)
    
    def visit_NonblockingSubstitution(self, node):
        self._process_assignment(node, "nonblocking")
        self.generic_visit(node)
    
    def _process_assignment(self, node, assign_type: str):
        try:
            lhs_vars = self._extract_variables(node.left)
            rhs_vars = self._extract_variables(node.right)
            
            logic_type = "combinational"
            if self.current_always_context:
                logic_type = self.current_always_context["logic_type"]
            
            for rhs_var in rhs_vars:
                for lhs_var in lhs_vars:
                    edge = {
                        "from": rhs_var,
                        "to": lhs_var,
                        "assign_type": assign_type,
                        "logic_type": logic_type,
                        "module": self.current_module
                    }
                    if self.current_always_context and self.current_always_context.get("sensitivity"):
                        edge["sensitivity"] = self.current_always_context["sensitivity"]
                    self.edges.append(edge)
        except Exception as e:
            print(f"警告：處理賦值語句時發生錯誤 - {str(e)}")
    
    def _extract_variables(self, node, variables=None) -> List[str]:
        if variables is None:
            variables = []
        try:
            if isinstance(node, Identifier):
                if node.name and node.name not in variables:
                    variables.append(node.name)
            elif isinstance(node, (Pointer, Partselect)):
                if hasattr(node, 'var'):
                    self._extract_variables(node.var, variables)
            elif isinstance(node, (UnaryOperator, Operator)):
                if hasattr(node, 'left'):
                    self._extract_variables(node.left, variables)
                if hasattr(node, 'right'):
                    self._extract_variables(node.right, variables)
            elif isinstance(node, Cond):
                if hasattr(node, 'true_value'):
                    self._extract_variables(node.true_value, variables)
                if hasattr(node, 'false_value'):
                    self._extract_variables(node.false_value, variables)
                if hasattr(node, 'cond'):
                    self._extract_variables(node.cond, variables)
            elif isinstance(node, (Concat, Repeat)):
                if hasattr(node, 'list'):
                    for item in node.list:
                        self._extract_variables(item, variables)
            elif isinstance(node, (Rvalue, Lvalue)):
                if hasattr(node, 'var'):
                    self._extract_variables(node.var, variables)
            elif isinstance(node, IntConst):
                pass
            elif hasattr(node, '__dict__'):
                for attr_value in node.__dict__.values():
                    if isinstance(attr_value, Node):
                        self._extract_variables(attr_value, variables)
                    elif isinstance(attr_value, (list, tuple)):
                        for item in attr_value:
                            if isinstance(item, Node):
                                self._extract_variables(item, variables)
        except Exception as e:
            print(f"警告：提取變數時發生錯誤 - {str(e)}")
        return variables
    # [新增] 捕捉子模組實例化，讓 FIFO_64, MAX_MIN 等模組出現
    def visit_InstanceList(self, node):
        for instance in node.instances:
            module_name = node.module # 被呼叫的模組名稱 (如 MAX_MIN)
            instance_id = instance.name # 實例名稱 (如 mm0)
            
            # 將子模組新增為圖形節點
            self.nodes.append({
                "id": instance_id,
                "type": "submodule",
                "label": f"{instance_id} ({module_name})",
                "module": self.current_module,
                "target_module": module_name  # 關鍵：新增目標模組欄位，用於前端展開
            })
            
            # 自動建立埠位連線 (Port Connections)
            for port in instance.portlist:
                port_name = port.portname # 內部的接腳
                arg_name = self._extract_signal_name(port.argname) # 外部連接的變數
                
                if arg_name:
                    # 建立外部變數到子模組的連線
                    self.edges.append({
                        "from": arg_name,
                        "to": instance_id,
                        "assign_type": "port_map",
                        "logic_type": "structural"
                    })
        self.generic_visit(node)

class VerilogParser:
    """
    Verilog 解析器主類別
    使用 PyVerilog 將 Verilog 原始碼解析為 AST，並提取硬體節點與連線資訊
    """
    
    def __init__(self):
        """初始化解析器"""
        self.include_paths = []  # Include 路徑列表
        self.define_macros = {}  # 定義的巨集
        
    def add_include_path(self, path: str):
        """
        新增 Include 路徑
        
        Args:
            path: Include 目錄路徑
        """
        if os.path.isdir(path):
            self.include_paths.append(path)
            print(f"已新增 Include 路徑：{path}")
        else:
            print(f"警告：Include 路徑不存在 - {path}")
    
    def add_define(self, name: str, value: str = ""):
        """
        新增巨集定義
        
        Args:
            name: 巨集名稱
            value: 巨集值
        """
        self.define_macros[name] = value
        print(f"已新增巨集定義：{name} = {value}")
    
    def parse_file(self, filepath: str) -> Dict[str, Any]:
        """
        解析 Verilog 檔案
        
        Args:
            filepath: Verilog 檔案路徑
            
        Returns:
            包含節點與連線資訊的字典
            格式：{"file": str, "nodes": List[Dict], "edges": List[Dict]}
            即便發生錯誤也會包含錯誤提示節點，確保後續 Stage 能正常運行
        """
        print(f"\n開始解析 Verilog 檔案：{filepath}")
        
        # 檢查檔案是否存在
        if not os.path.isfile(filepath):
            error_msg = f"檔案不存在：{filepath}"
            print(f"錯誤：{error_msg}")
            # 回傳錯誤提示節點，而非頂層 error 欄位
            return {
                "file": filepath,
                "nodes": [
                    {
                        "id": "ERROR_FILE_NOT_FOUND",
                        "type": "error",
                        "width": 1,
                        "module": "parse_error",
                        "error_message": error_msg
                    }
                ],
                "edges": []
            }
        
        try:
            # 設定環境變數強制 UTF-8（PyVerilog 預處理器會使用）
            old_lang = os.environ.get('LANG', '')
            old_pythonioencoding = os.environ.get('PYTHONIOENCODING', '')
            
            os.environ['LANG'] = 'en_US.UTF-8'
            os.environ['PYTHONIOENCODING'] = 'utf-8:ignore'
            
            # 強制使用 UTF-8 編碼處理檔案
            temp_filepath = None
            try:
                # 讀取原始檔案並轉換為 UTF-8
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # 建立臨時 UTF-8 檔案
                import tempfile
                temp_fd, temp_filepath = tempfile.mkstemp(suffix='.v', text=False)
                # 明確以 UTF-8 bytes 寫入
                with os.fdopen(temp_fd, 'wb') as f:
                    f.write(content.encode('utf-8'))
                
                print(f"已建立 UTF-8 臨時檔案：{temp_filepath}")
                parse_filepath = temp_filepath
                
            except Exception as e:
                print(f"警告：UTF-8 轉換失敗，使用原始檔案 - {str(e)}")
                parse_filepath = filepath
            
            # 準備解析參數
            parse_args = [parse_filepath]
            
            # 加入 Include 路徑
            for include_path in self.include_paths:
                parse_args.extend(['-I', include_path])
            
            # 加入巨集定義
            for macro_name, macro_value in self.define_macros.items():
                if macro_value:
                    parse_args.extend(['-D', f"{macro_name}={macro_value}"])
                else:
                    parse_args.extend(['-D', macro_name])
            
            print(f"解析參數：{parse_args}")
            
            # 猴子補丁：覆蓋 builtins.open 強制使用 UTF-8
            # 這是為了解決 PyVerilog 內部使用系統預設編碼的問題
            import builtins
            original_open = builtins.open
            
            def utf8_open(file, mode='r', *args, **kwargs):
                """強制 UTF-8 的 open 函數"""
                if 'b' not in mode and 'encoding' not in kwargs:
                    kwargs['encoding'] = 'utf-8'
                    kwargs['errors'] = 'ignore'
                return original_open(file, mode, *args, **kwargs)
            
            # 暫時替換 open 函數
            builtins.open = utf8_open
            
            try:
                # 使用 PyVerilog 解析檔案
                ast, directives = parse(
                    parse_args,
                    preprocess_include=self.include_paths,
                    preprocess_define=self.define_macros
                )
            finally:
                # 恢復原始 open 函數
                builtins.open = original_open
            
            if ast is None:
                error_msg = "PyVerilog 解析失敗，無法產生 AST"
                print(f"錯誤：{error_msg}")
                # 回傳錯誤提示節點
                return {
                    "file": filepath,
                    "nodes": [
                        {
                            "id": "ERROR_AST_PARSE_FAILED",
                            "type": "error",
                            "width": 1,
                            "module": "parse_error",
                            "error_message": error_msg
                        }
                    ],
                    "edges": []
                }
            
            print("AST 解析成功，開始提取硬體元件...")
            
            # 恢復環境變數
            if old_lang:
                os.environ['LANG'] = old_lang
            elif 'LANG' in os.environ:
                del os.environ['LANG']
            
            if old_pythonioencoding:
                os.environ['PYTHONIOENCODING'] = old_pythonioencoding
            elif 'PYTHONIOENCODING' in os.environ:
                del os.environ['PYTHONIOENCODING']
            
            # 清理臨時檔案
            if temp_filepath and os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                    print(f"已清理臨時檔案：{temp_filepath}")
                except:
                    pass
            
            # 建立訪問器並遍歷 AST
            visitor = VerilogASTVisitor()
            visitor.visit(ast)
            
            # 輸出統計資訊
            print(f"\n解析完成！")
            print(f"  提取節點數量：{len(visitor.nodes)}")
            print(f"  提取連線數量：{len(visitor.edges)}")
            
            # 檢查是否提取到任何節點
            if len(visitor.nodes) == 0:
                print("警告：未提取到任何硬體節點，可能檔案為空或格式不正確")
                # 建立一個警告節點
                visitor.nodes.append({
                    "id": "WARNING_NO_NODES_FOUND",
                    "type": "warning",
                    "width": 1,
                    "module": "parse_warning",
                    "error_message": "未提取到任何硬體節點"
                })
            
            # 回傳結果（不包含頂層 error 欄位）
            return {
                "file": filepath,
                "nodes": visitor.nodes,
                "edges": visitor.edges
            }
            
        except Exception as e:
            # 恢復環境變數
            if 'old_lang' in locals():
                if old_lang:
                    os.environ['LANG'] = old_lang
                elif 'LANG' in os.environ:
                    del os.environ['LANG']
            
            if 'old_pythonioencoding' in locals():
                if old_pythonioencoding:
                    os.environ['PYTHONIOENCODING'] = old_pythonioencoding
                elif 'PYTHONIOENCODING' in os.environ:
                    del os.environ['PYTHONIOENCODING']
            
            # 清理臨時檔案
            if 'temp_filepath' in locals() and temp_filepath and os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except:
                    pass
            
            error_msg = f"解析過程中發生異常：{str(e)}"
            print(f"錯誤：{error_msg}")
            import traceback
            traceback.print_exc()
            
            # 回傳錯誤提示節點，而非頂層 error 欄位
            return {
                "file": filepath,
                "nodes": [
                    {
                        "id": "ERROR_EXCEPTION",
                        "type": "error",
                        "width": 1,
                        "module": "parse_error",
                        "error_message": error_msg
                    }
                ],
                "edges": []
            }
    
    def parse_files(self, filepaths: List[str]) -> List[Dict[str, Any]]:
        """
        批次解析多個 Verilog 檔案
        
        Args:
            filepaths: Verilog 檔案路徑列表
            
        Returns:
            解析結果列表
        """
        results = []
        
        print(f"\n準備批次解析 {len(filepaths)} 個 Verilog 檔案")
        
        for i, filepath in enumerate(filepaths, 1):
            print(f"\n進度：{i}/{len(filepaths)}")
            result = self.parse_file(filepath)
            results.append(result)
        
        print(f"\n批次解析完成！")
        
        # 統計總計
        total_nodes = sum(len(r.get("nodes", [])) for r in results)
        total_edges = sum(len(r.get("edges", [])) for r in results)
        error_count = sum(1 for r in results if "error" in r)
        
        print(f"  總節點數量：{total_nodes}")
        print(f"  總連線數量：{total_edges}")
        print(f"  錯誤檔案數：{error_count}")
        
        return results


def main():
    """
    主函式：提供命令列介面測試
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Verilog 硬體描述語言解析器 - 提取硬體節點與連線資訊"
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="要解析的 Verilog 檔案路徑"
    )
    parser.add_argument(
        "-I", "--include",
        action="append",
        dest="includes",
        default=[],
        help="Include 目錄路徑"
    )
    parser.add_argument(
        "-D", "--define",
        action="append",
        dest="defines",
        default=[],
        help="巨集定義（格式：NAME 或 NAME=VALUE）"
    )
    parser.add_argument(
        "-o", "--output",
        help="輸出 JSON 檔案路徑"
    )
    
    args = parser.parse_args()
    
    # 建立解析器
    verilog_parser = VerilogParser()
    
    # 加入 Include 路徑
    for include_path in args.includes:
        verilog_parser.add_include_path(include_path)
    
    # 加入巨集定義
    for define in args.defines:
        if '=' in define:
            name, value = define.split('=', 1)
            verilog_parser.add_define(name, value)
        else:
            verilog_parser.add_define(define)
    
    # 解析檔案
    if len(args.files) == 1:
        result = verilog_parser.parse_file(args.files[0])
        results = [result]
    else:
        results = verilog_parser.parse_files(args.files)
    
    # 輸出結果
    if args.output:
        import json
        output_path = args.output
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n結果已儲存至：{output_path}")
        except Exception as e:
            print(f"\n錯誤：無法儲存結果檔案 - {str(e)}")
    else:
        # 列印簡要資訊
        import json
        print("\n" + "=" * 60)
        print("解析結果：")
        print("=" * 60)
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
