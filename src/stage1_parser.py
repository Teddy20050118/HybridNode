"""
階段 1：基於 libclang 的高精確度解析器
功能：解析 C/C++ 源代碼，提取函數、類別、變數及其依賴關係
"""

import json
import os
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from clang.cindex import (
    Index, 
    CursorKind, 
    TypeKind, 
    TranslationUnit,
    Cursor,
    Config
)


class ComplexityAnalyzer:
    """計算圈複雜度（Cyclomatic Complexity）"""
    
    # 增加複雜度的語句類型
    COMPLEXITY_NODES = {
        CursorKind.IF_STMT,
        CursorKind.WHILE_STMT,
        CursorKind.FOR_STMT,
        CursorKind.CASE_STMT,
        CursorKind.DEFAULT_STMT,
        CursorKind.CONDITIONAL_OPERATOR,  # 三元運算符
        CursorKind.CXX_CATCH_STMT,
    }
    
    @staticmethod
    def calculate(cursor: Cursor) -> int:
        """
        計算函數的圈複雜度
        公式：CC = E - N + 2P (E=邊數, N=節點數, P=連通分量)
        簡化實現：CC = 1 + 決策點數量
        """
        complexity = 1  # 基礎複雜度
        
        def traverse(node: Cursor):
            nonlocal complexity
            if node.kind in ComplexityAnalyzer.COMPLEXITY_NODES:
                complexity += 1
            
            # 處理邏輯運算符 (AND, OR)
            if node.kind == CursorKind.BINARY_OPERATOR:
                tokens = list(node.get_tokens())
                for token in tokens:
                    if token.spelling in ('&&', '||'):
                        complexity += 1
            
            for child in node.get_children():
                traverse(child)
        
        traverse(cursor)
        return complexity


class ClangParser:
    """基於 libclang 的 C/C++ 源碼解析器"""
    
    def __init__(self, libclang_path: Optional[str] = None):
        """
        初始化解析器
        
        Args:
            libclang_path: libclang 動態庫路徑（可選）
        """
        if libclang_path:
            Config.set_library_file(libclang_path)
        
        self.index = Index.create()
        self.nodes: List[Dict] = []
        self.edges: List[Dict] = []
        self.file_asts: Dict[str, TranslationUnit] = {}
        
        # 用於跨文件分析的全局符號表
        self.global_symbols: Dict[str, Dict] = {}
        self.function_calls: List[Tuple[str, str, str]] = []  # (caller, callee, location)
        
    def _auto_include_args(self, filepath: str) -> List[str]:
        """
        [INFO] 自動探索與檔案相鄰的 include 路徑並轉為 -I 編譯參數。
        規則：檔案所在目錄、同層 include/includes/headers/inc 子目錄、
        向上至多 3 層父目錄同樣做相同探索。
        """
        args: List[str] = []
        candidate = Path(filepath).resolve().parent
        for _ in range(4):
            args.append(f'-I{candidate}')
            for sub in ('include', 'includes', 'headers', 'inc'):
                sub_path = candidate / sub
                if sub_path.is_dir():
                    args.append(f'-I{sub_path}')
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent
        return args

    def parse_file(self, filepath: str, compilation_args: Optional[List[str]] = None) -> TranslationUnit:
        """
        [INFO] 解析單個 C/C++ 文件。
        已移除 PARSE_SKIP_FUNCTION_BODIES — 此 flag 令 libclang 跳過
        所有函數體 AST 節點，導致 CALL_EXPR / CXX_MEMBER_CALL_EXPR
        完全不存在於 AST 中，是 Total Links=0 的根本原因。
        """
        if compilation_args is None:
            compilation_args = [
                '-std=c++14',
                '-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH',
                '-Wno-everything',
            ] + self._auto_include_args(filepath)

        try:
            tu = self.index.parse(
                filepath,
                args=compilation_args,
                # [INFO] 只保留 PARSE_DETAILED_PROCESSING_RECORD，
                # 不加 PARSE_SKIP_FUNCTION_BODIES
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            )

            errors = [d for d in tu.diagnostics if d.severity >= 3]
            if errors:
                print(f"[WARN] {filepath} 解析時出現錯誤：")
                for error in errors[:3]:
                    print(f"   - {error.spelling}")

            self.file_asts[filepath] = tu
            return tu

        except Exception as e:
            print(f"[WARN] 無法解析 {filepath} - {str(e)}")
            return None


    def extract_function_info(self, cursor: Cursor) -> Optional[Dict]:
        """提取函數聲明信息"""
        if cursor.kind not in (CursorKind.FUNCTION_DECL, CursorKind.CXX_METHOD):
            return None
        
        # 獲取函數簽名
        params = []
        for arg in cursor.get_arguments():
            params.append({
                'name': arg.spelling,
                'type': arg.type.spelling
            })
        
        # 計算圈複雜度和行數
        complexity = ComplexityAnalyzer.calculate(cursor)
        
        # 獲取定義範圍
        extent = cursor.extent
        line_count = extent.end.line - extent.start.line + 1 if extent.start.line > 0 else 0
        
        function_info = {
            'id': cursor.hash,
            'type': 'FunctionDecl',
            'name': cursor.spelling,
            'qualified_name': cursor.displayname,
            'return_type': cursor.result_type.spelling,
            'parameters': params,
            'cyclomatic_complexity': complexity,
            'line_count': line_count,
            'location': {
                'file': str(cursor.location.file) if cursor.location.file else None,
                'line': cursor.location.line,
                'column': cursor.location.column
            },
            'is_definition': cursor.is_definition(),
            'access_specifier': str(cursor.access_specifier)
        }
        
        # 記錄到全局符號表
        self.global_symbols[cursor.spelling] = function_info
        
        return function_info
    
    def extract_class_info(self, cursor: Cursor) -> Optional[Dict]:
        """提取類別/結構體信息"""
        if cursor.kind not in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
            return None
        
        # 提取成員變數和方法
        members = []
        methods = []
        base_classes = []
        
        for child in cursor.get_children():
            if child.kind == CursorKind.FIELD_DECL:
                members.append({
                    'name': child.spelling,
                    'type': child.type.spelling,
                    'access': str(child.access_specifier)
                })
            elif child.kind == CursorKind.CXX_METHOD:
                methods.append({
                    'name': child.spelling,
                    'signature': child.displayname
                })
            elif child.kind == CursorKind.CXX_BASE_SPECIFIER:
                base_classes.append({
                    'name': child.type.spelling,
                    'access': str(child.access_specifier)
                })
        
        class_info = {
            'id': cursor.hash,
            'type': 'CXXRecordDecl',
            'name': cursor.spelling,
            'kind': 'class' if cursor.kind == CursorKind.CLASS_DECL else 'struct',
            'members': members,
            'methods': methods,
            'base_classes': base_classes,
            'location': {
                'file': str(cursor.location.file) if cursor.location.file else None,
                'line': cursor.location.line
            }
        }
        
        self.global_symbols[cursor.spelling] = class_info
        return class_info
    
    def extract_variable_info(self, cursor: Cursor) -> Optional[Dict]:
        """提取全局變數信息"""
        if cursor.kind != CursorKind.VAR_DECL:
            return None
        
        # 只提取全局變數（不在函數內部）
        if cursor.semantic_parent and cursor.semantic_parent.kind == CursorKind.FUNCTION_DECL:
            return None
        
        var_info = {
            'id': cursor.hash,
            'type': 'VarDecl',
            'name': cursor.spelling,
            'var_type': cursor.type.spelling,
            'is_const': cursor.type.is_const_qualified(),
            'location': {
                'file': str(cursor.location.file) if cursor.location.file else None,
                'line': cursor.location.line
            }
        }
        
        return var_info
    
    def extract_call_edges(self, cursor: Cursor, caller_name: str = None):
        """提取函數調用關係"""
        if cursor.kind == CursorKind.CALL_EXPR:
            callee = cursor.referenced
            if callee and callee.kind == CursorKind.FUNCTION_DECL:
                edge = {
                    'type': 'CallExpr',
                    'from': caller_name,
                    'to': callee.spelling,
                    'location': {
                        'file': str(cursor.location.file) if cursor.location.file else None,
                        'line': cursor.location.line
                    }
                }
                self.edges.append(edge)
        
        # 遞歸處理子節點
        for child in cursor.get_children():
            self.extract_call_edges(child, caller_name)
    
    def extract_inheritance_edges(self, cursor: Cursor):
        """提取類別繼承關係"""
        for child in cursor.get_children():
            if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                edge = {
                    'type': 'BaseSpecifier',
                    'from': cursor.spelling,
                    'to': child.type.spelling,
                    'access': str(child.access_specifier)
                }
                self.edges.append(edge)
    
    def extract_member_access_edges(self, cursor: Cursor, context_name: str = None):
        """提取成員變數存取關係"""
        if cursor.kind == CursorKind.MEMBER_REF_EXPR:
            member = cursor.referenced
            if member:
                edge = {
                    'type': 'MemberRefExpr',
                    'from': context_name,
                    'to': member.spelling,
                    'member_type': member.type.spelling if hasattr(member, 'type') else 'unknown'
                }
                self.edges.append(edge)
        
        for child in cursor.get_children():
            self.extract_member_access_edges(child, context_name)
    
    def traverse_ast(self, cursor: Cursor, depth: int = 0):
        """遞歸遍歷 AST"""
        # 只處理當前項目的文件（過濾系統頭文件）
        if cursor.location.file:
            file_path = str(cursor.location.file)
            if 'include' in file_path.lower() or 'usr' in file_path.lower():
                return
        
        # 提取節點信息
        if cursor.kind == CursorKind.FUNCTION_DECL or cursor.kind == CursorKind.CXX_METHOD:
            func_info = self.extract_function_info(cursor)
            if func_info:
                self.nodes.append(func_info)
                # 提取函數內的調用關係
                self.extract_call_edges(cursor, cursor.spelling)
                self.extract_member_access_edges(cursor, cursor.spelling)
        
        elif cursor.kind in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
            class_info = self.extract_class_info(cursor)
            if class_info and cursor.is_definition():
                self.nodes.append(class_info)
                self.extract_inheritance_edges(cursor)
        
        elif cursor.kind == CursorKind.VAR_DECL:
            var_info = self.extract_variable_info(cursor)
            if var_info:
                self.nodes.append(var_info)
        
        # 遞歸處理子節點
        for child in cursor.get_children():
            self.traverse_ast(child, depth + 1)
    
    def analyze_project(self, source_files: List[str], include_paths: Optional[List[str]] = None) -> Dict:
        """
        分析整個項目（支持跨文件分析）
        
        Args:
            source_files: 源文件列表
            include_paths: 頭文件搜索路徑
            
        Returns:
            包含 nodes 和 edges 的字典
        """
        compilation_args = [
            '-std=c++14',
            '-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH',
            '-Wno-everything',
        ]
        if include_paths:
            for path in include_paths:
                compilation_args.append(f'-I{path}')
        
        print(f"開始解析 {len(source_files)} 個文件...")
        
        # 第一階段：解析所有文件並建立符號表
        for filepath in source_files:
            if not os.path.exists(filepath):
                print(f"警告：文件不存在 - {filepath}")
                continue
            
            print(f"   解析：{filepath}")
            tu = self.parse_file(filepath, compilation_args)
            if tu is not None:
                self.traverse_ast(tu.cursor)
        
        # 生成分析報告
        result = {
            'nodes': self.nodes,
            'edges': self.edges,
            'statistics': {
                'total_files': len(source_files),
                'total_nodes': len(self.nodes),
                'total_edges': len(self.edges),
                'functions': len([n for n in self.nodes if n['type'] == 'FunctionDecl']),
                'classes': len([n for n in self.nodes if n['type'] == 'CXXRecordDecl']),
                'variables': len([n for n in self.nodes if n['type'] == 'VarDecl'])
            }
        }
        
        print(f"解析完成")
        print(f"   - 節點數：{result['statistics']['total_nodes']}")
        print(f"   - 邊數：{result['statistics']['total_edges']}")
        
        return result
    
    def parse_file_safe(self, filepath: str, compilation_args: Optional[List[str]] = None) -> Dict:
        """
        安全地解析單個檔案並返回可序列化的字典資料
        
        Args:
            filepath: 文件路徑
            compilation_args: 編譯參數
            
        Returns:
            Dict: 包含 nodes 和 edges 的可序列化字典（不包含 TranslationUnit）
        """
        # 解析文件
        tu = self.parse_file(filepath, compilation_args)
        if tu is None:
            return {
                'file': filepath,
                'nodes': [],
                'edges': [],
                'error': '解析失敗'
            }
        
        # 儲存當前狀態
        nodes_before = len(self.nodes)
        edges_before = len(self.edges)
        
        # 遍歷 AST 提取資訊
        self.traverse_ast(tu.cursor)
        
        # 提取本次新增的節點和邊
        new_nodes = self.nodes[nodes_before:]
        new_edges = self.edges[edges_before:]
        
        # 返回可序列化的資料（不包含 tu 物件）
        return {
            'file': filepath,
            'nodes': new_nodes,
            'edges': new_edges,
            'statistics': {
                'node_count': len(new_nodes),
                'edge_count': len(new_edges)
            }
        }
    
    def export_to_json(self, output_path: str):
        """將分析結果導出為 JSON"""
        result = {
            'nodes': self.nodes,
            'edges': self.edges,
            'statistics': {
                'total_nodes': len(self.nodes),
                'total_edges': len(self.edges)
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"已儲存至：{output_path}")


def find_source_files(directory: str, extensions: Tuple[str, ...] = ('.cpp', '.c', '.cc', '.h', '.hpp')) -> List[str]:
    """
    遞歸查找目錄下的所有源文件
    
    Args:
        directory: 搜索目錄
        extensions: 文件擴展名
        
    Returns:
        源文件路徑列表
    """
    source_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(extensions):
                source_files.append(os.path.join(root, file))
    return source_files


if __name__ == "__main__":
    # 使用示例
    parser = ClangParser()
    
    # 解析單個文件
    # tu = parser.parse_file("example.cpp")
    # parser.traverse_ast(tu.cursor)
    
    # 解析項目目錄
    # source_files = find_source_files("./src")
    # result = parser.analyze_project(source_files)
    # parser.export_to_json("output.json")
    
    print("階段 1 解析器已就緒！")
