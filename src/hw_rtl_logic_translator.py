"""
RTL 邏輯轉換器 (RTL-to-Gate Translation)
功能：將 RTL 層級的 if/case/assign 轉換為閘級邏輯 (MUX, AND, OR, XOR)
"""

from pyverilog.vparser.ast import *


class RTLLogicTranslator:
    """
    RTL 邏輯轉換器
    將高階 RTL 結構轉換為可視覺化的硬體元件
    """
    
    def __init__(self):
        self.gate_nodes = []        # 產生的閘級節點清單
        self.mux_counter = 0        # MUX 節點計數器
        self.gate_counter = 0       # 邏輯閘計數器
        
    def translate_module(self, ast_module):
        """
        轉換整個模組的邏輯
        
        Args:
            ast_module: Module AST 節點
            
        Returns:
            list: 閘級節點清單
        """
        self.gate_nodes = []
        
        # 遍歷模組內的所有項目
        for item in ast_module.items:
            if isinstance(item, Always):
                self._translate_always_block(item)
            elif isinstance(item, Assign):
                self._translate_assign(item)
        
        return self.gate_nodes
    
    def _translate_always_block(self, always_node):
        """
        轉換 Always 區塊
        
        Args:
            always_node: Always AST 節點
            
        範例 Verilog:
            always @(*) begin
                if (sel)
                    out = a;
                else
                    out = b;
            end
            
        轉換為: MUX(sel, a, b) -> out
        """
        if always_node.statement is None:
            return
        
        # 處理 Block 內的語句
        if isinstance(always_node.statement, Block):
            for stmt in always_node.statement.statements:
                self._translate_statement(stmt)
        else:
            self._translate_statement(always_node.statement)
    
    def _translate_statement(self, stmt):
        """
        轉換單一語句
        
        Args:
            stmt: 語句節點 (IfStatement, CaseStatement, NonblockingSubstitution 等)
        """
        if isinstance(stmt, IfStatement):
            self._translate_if_to_mux(stmt)
        elif isinstance(stmt, CaseStatement):
            self._translate_case_to_mux(stmt)
        elif isinstance(stmt, Block):
            for sub_stmt in stmt.statements:
                self._translate_statement(sub_stmt)
    
    def _translate_if_to_mux(self, if_stmt):
        """
        將 If 語句轉換為 MUX 節點
        
        Args:
            if_stmt: IfStatement AST 節點
            
        轉換邏輯:
            if (cond)
                target = true_value;
            else
                target = false_value;
                
        等同於:
            target = MUX(cond, true_value, false_value);
        """
        # 提取條件表達式
        condition = self._extract_expression_name(if_stmt.cond)
        
        # 提取目標訊號與真值
        true_target, true_value = self._extract_assignment(if_stmt.true_statement)
        
        # 提取假值
        false_value = None
        if if_stmt.false_statement:
            _, false_value = self._extract_assignment(if_stmt.false_statement)
        
        if true_target is None:
            return
        
        # 建立 MUX 節點
        mux_node = {
            'id': f'mux_{self.mux_counter}',
            'type': 'MUX',
            'label': f'MUX_{self.mux_counter}',
            'inputs': {
                'sel': condition,
                'in1': true_value if true_value else 'unknown',
                'in0': false_value if false_value else 'unknown'
            },
            'output': true_target,
            'source_line': if_stmt.lineno if hasattr(if_stmt, 'lineno') else None
        }
        
        self.gate_nodes.append(mux_node)
        self.mux_counter += 1
        
        print(f'[RTL->Gate] 偵測到 MUX: {condition} ? {true_value} : {false_value} -> {true_target}')
    
    def _translate_case_to_mux(self, case_stmt):
        """
        將 Case 語句轉換為多層 MUX
        
        Args:
            case_stmt: CaseStatement AST 節點
            
        轉換邏輯:
            case (sel)
                2'b00: out = a;
                2'b01: out = b;
                2'b10: out = c;
                2'b11: out = d;
            endcase
            
        等同於:
            MUX_tree(sel[1:0], {a, b, c, d})
        """
        # 提取選擇訊號
        selector = self._extract_expression_name(case_stmt.comp)
        
        # 提取所有 case 項目
        case_items = []
        for case_item in case_stmt.caselist:
            if isinstance(case_item, Case):
                cond = self._extract_expression_name(case_item.cond[0]) if case_item.cond else 'default'
                target, value = self._extract_assignment(case_item.statement)
                case_items.append({'cond': cond, 'target': target, 'value': value})
        
        # 建立 MUX Tree 節點
        mux_tree_node = {
            'id': f'mux_tree_{self.mux_counter}',
            'type': 'MUX_TREE',
            'label': f'CASE_MUX_{self.mux_counter}',
            'selector': selector,
            'cases': case_items,
            'source_line': case_stmt.lineno if hasattr(case_stmt, 'lineno') else None
        }
        
        self.gate_nodes.append(mux_tree_node)
        self.mux_counter += 1
        
        print(f'[RTL->Gate] 偵測到 CASE MUX: {selector} -> {len(case_items)} 分支')
    
    def _translate_assign(self, assign_node):
        """
        轉換 Assign 語句中的邏輯運算
        
        Args:
            assign_node: Assign AST 節點
            
        範例:
            assign out = a & b | c;
            
        轉換為:
            AND_0(a, b) -> temp_0
            OR_0(temp_0, c) -> out
        """
        left = assign_node.left.var
        right = assign_node.right.var
        
        target_name = self._extract_expression_name(left)
        
        # 分析右側表達式
        gate_chain = self._analyze_expression(right)
        
        if gate_chain:
            # 將最終輸出連接到目標訊號
            gate_chain[-1]['output'] = target_name
            self.gate_nodes.extend(gate_chain)
    
    def _analyze_expression(self, expr):
        """
        遞迴分析表達式樹，轉換為邏輯閘鏈
        
        Args:
            expr: 表達式節點
            
        Returns:
            list: 邏輯閘節點清單
        """
        gate_chain = []
        
        # 處理二元運算 (AND, OR, XOR)
        if isinstance(expr, (And, Or, Xor)):
            gate_type = self._get_gate_type(expr)
            
            left_name = self._extract_expression_name(expr.left)
            right_name = self._extract_expression_name(expr.right)
            
            gate_node = {
                'id': f'gate_{self.gate_counter}',
                'type': gate_type,
                'label': f'{gate_type}_{self.gate_counter}',
                'inputs': [left_name, right_name],
                'output': f'temp_{self.gate_counter}',
                'source_line': expr.lineno if hasattr(expr, 'lineno') else None
            }
            
            gate_chain.append(gate_node)
            self.gate_counter += 1
            
            print(f'[RTL->Gate] 偵測到 {gate_type} 閘: {left_name} {gate_type} {right_name}')
        
        # 處理 NOT 運算
        elif isinstance(expr, Unot):
            operand_name = self._extract_expression_name(expr.right)
            
            gate_node = {
                'id': f'gate_{self.gate_counter}',
                'type': 'NOT',
                'label': f'NOT_{self.gate_counter}',
                'inputs': [operand_name],
                'output': f'temp_{self.gate_counter}',
                'source_line': expr.lineno if hasattr(expr, 'lineno') else None
            }
            
            gate_chain.append(gate_node)
            self.gate_counter += 1
            
            print(f'[RTL->Gate] 偵測到 NOT 閘: ~{operand_name}')
        
        return gate_chain
    
    def _get_gate_type(self, expr):
        """
        取得運算子對應的邏輯閘類型
        
        Args:
            expr: 表達式節點
            
        Returns:
            str: 'AND', 'OR', 'XOR', 'NAND', 'NOR'
        """
        if isinstance(expr, And):
            return 'AND'
        elif isinstance(expr, Or):
            return 'OR'
        elif isinstance(expr, Xor):
            return 'XOR'
        else:
            return 'UNKNOWN'
    
    def _extract_assignment(self, stmt):
        """
        從賦值語句中提取目標與值
        
        Args:
            stmt: 語句節點
            
        Returns:
            tuple: (target_name, value_name)
        """
        if stmt is None:
            return None, None
        
        # 處理 Block
        if isinstance(stmt, Block):
            if stmt.statements:
                stmt = stmt.statements[0]
            else:
                return None, None
        
        # 處理 NonblockingSubstitution 或 BlockingSubstitution
        if isinstance(stmt, (NonblockingSubstitution, BlockingSubstitution)):
            target = self._extract_expression_name(stmt.left.var)
            value = self._extract_expression_name(stmt.right.var)
            return target, value
        
        return None, None
    
    def _extract_expression_name(self, expr):
        """
        從表達式中提取名稱或常數
        
        Args:
            expr: 表達式節點
            
        Returns:
            str: 訊號名稱或常數值
        """
        if expr is None:
            return 'unknown'
        
        if isinstance(expr, Identifier):
            return expr.name
        elif isinstance(expr, IntConst):
            return expr.value
        elif isinstance(expr, Pointer):
            if isinstance(expr.var, Identifier):
                return expr.var.name
        elif isinstance(expr, (And, Or, Xor)):
            # 遞迴處理複合表達式
            left = self._extract_expression_name(expr.left)
            right = self._extract_expression_name(expr.right)
            op = self._get_gate_type(expr)
            return f'{left}_{op}_{right}'
        
        return str(expr)
    
    def export_to_react_flow(self):
        """
        將閘級節點轉換為 React Flow 節點格式
        
        Returns:
            list: React Flow 節點清單
        """
        react_nodes = []
        
        for gate in self.gate_nodes:
            node = {
                'id': gate['id'],
                'type': 'gateNode',  # 自定義節點類型
                'data': {
                    'label': gate['label'],
                    'gate_type': gate['type'],
                    'inputs': gate.get('inputs', []),
                    'output': gate.get('output', ''),
                    'source_line': gate.get('source_line')
                },
                'position': {'x': 0, 'y': 0}  # 需後續佈局計算
            }
            react_nodes.append(node)
        
        return react_nodes


# 使用範例
if __name__ == '__main__':
    """
    測試範例：轉換以下 RTL 邏輯
    
    always @(*) begin
        if (sel)
            out = a & b;
        else
            out = c | d;
    end
    """
    translator = RTLLogicTranslator()
    
    # 模擬 AST 處理 (實際需從 PyVerilog 解析結果取得)
    # gates = translator.translate_module(ast_module)
    # react_nodes = translator.export_to_react_flow()
    
    print('RTL 邏輯轉換器已就緒')
    print('支援轉換: IF->MUX, CASE->MUX_TREE, ASSIGN->AND/OR/XOR')
