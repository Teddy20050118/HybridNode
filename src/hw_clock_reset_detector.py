"""
硬體時脈與重置訊號偵測器
功能：遍歷 PyVerilog AST 的敏感列表 (Sensitivity List)，識別時脈與重置訊號
"""

from pyverilog.vparser.ast import *


class ClockResetDetector:
    """
    時序控制訊號偵測器
    分析 always 區塊的敏感列表，自動標記時脈與重置訊號
    """
    
    def __init__(self):
        self.clock_signals = set()      # 時脈訊號集合
        self.reset_signals = set()      # 重置訊號集合
        self.posedge_signals = set()    # 正緣觸發訊號
        self.negedge_signals = set()    # 負緣觸發訊號
        
    def analyze(self, ast_root):
        """
        主要分析入口
        
        Args:
            ast_root: PyVerilog AST 根節點
            
        Returns:
            dict: 包含時脈與重置訊號的字典
        """
        self._traverse_ast(ast_root)
        
        return {
            'clocks': list(self.clock_signals),
            'resets': list(self.reset_signals),
            'posedge': list(self.posedge_signals),
            'negedge': list(self.negedge_signals),
            'metadata': {
                'total_clocks': len(self.clock_signals),
                'total_resets': len(self.reset_signals)
            }
        }
    
    def _traverse_ast(self, node):
        """
        遞迴遍歷 AST 節點
        
        Args:
            node: 當前 AST 節點
        """
        if node is None:
            return
            
        # 偵測 Always 區塊
        if isinstance(node, Always):
            self._analyze_always_block(node)
            
        # 遞迴處理子節點
        for child in node.children():
            self._traverse_ast(child)
    
    def _analyze_always_block(self, always_node):
        """
        分析 Always 區塊的敏感列表
        
        Args:
            always_node: Always AST 節點
            
        範例 Verilog:
            always @(posedge clk or negedge rst_n) begin
                // ...
            end
        """
        if always_node.senslist is None:
            return
        
        sens_list = always_node.senslist
        
        # 遍歷敏感列表中的每個元素
        if isinstance(sens_list, SensList):
            for sens in sens_list.list:
                self._analyze_sensitivity(sens)
    
    def _analyze_sensitivity(self, sens):
        """
        分析單一敏感訊號
        
        Args:
            sens: Sens 節點 (包含 type 與 sig)
            
        敏感類型:
            - posedge: 正緣觸發 (通常是時脈)
            - negedge: 負緣觸發 (可能是時脈或低態重置)
            - all: 組合邏輯
        """
        if not isinstance(sens, Sens):
            return
        
        # 取得訊號名稱
        signal_name = self._extract_signal_name(sens.sig)
        
        if signal_name is None:
            return
        
        # 分析敏感類型
        sens_type = sens.type
        
        if sens_type == 'posedge':
            self.posedge_signals.add(signal_name)
            
            # 啟發式規則：名稱包含 'clk' 或 'clock' 的正緣訊號為時脈
            if self._is_clock_name(signal_name):
                self.clock_signals.add(signal_name)
            else:
                # 正緣但非典型時脈名稱，可能是 enable 訊號
                pass
                
        elif sens_type == 'negedge':
            self.negedge_signals.add(signal_name)
            
            # 啟發式規則：名稱包含 'rst', 'reset', 'rstn' 的負緣訊號為重置
            if self._is_reset_name(signal_name):
                self.reset_signals.add(signal_name)
            else:
                # 負緣但非典型重置名稱，可能是負緣時脈
                if self._is_clock_name(signal_name):
                    self.clock_signals.add(signal_name)
    
    def _extract_signal_name(self, sig_node):
        """
        從訊號節點中提取名稱
        
        Args:
            sig_node: 訊號節點 (Identifier, Pointer 等)
            
        Returns:
            str: 訊號名稱
        """
        if isinstance(sig_node, Identifier):
            return sig_node.name
        elif isinstance(sig_node, Pointer):
            # 處理陣列型訊號 (例如：clk[0])
            if isinstance(sig_node.var, Identifier):
                return sig_node.var.name
        
        return None
    
    def _is_clock_name(self, name):
        """
        判斷訊號名稱是否符合時脈命名慣例
        
        Args:
            name (str): 訊號名稱
            
        Returns:
            bool: 是否為時脈訊號
            
        常見時脈命名:
            - clk, clock, CLK, CLOCK
            - sys_clk, core_clk, axi_clk
            - clk_in, clk_out
        """
        name_lower = name.lower()
        
        clock_keywords = ['clk', 'clock']
        
        for keyword in clock_keywords:
            if keyword in name_lower:
                return True
        
        return False
    
    def _is_reset_name(self, name):
        """
        判斷訊號名稱是否符合重置命名慣例
        
        Args:
            name (str): 訊號名稱
            
        Returns:
            bool: 是否為重置訊號
            
        常見重置命名:
            - rst, reset, RST, RESET
            - rst_n, rstn, reset_n (低態有效)
            - arst, srst (非同步/同步重置)
            - sys_rst, core_rst
        """
        name_lower = name.lower()
        
        reset_keywords = ['rst', 'reset']
        
        for keyword in reset_keywords:
            if keyword in name_lower:
                return True
        
        return False
    
    def get_signal_attributes(self, signal_name):
        """
        查詢特定訊號的屬性
        
        Args:
            signal_name (str): 訊號名稱
            
        Returns:
            dict: 訊號屬性
        """
        return {
            'is_clock': signal_name in self.clock_signals,
            'is_reset': signal_name in self.reset_signals,
            'is_posedge': signal_name in self.posedge_signals,
            'is_negedge': signal_name in self.negedge_signals,
            'timing_role': self._get_timing_role(signal_name)
        }
    
    def _get_timing_role(self, signal_name):
        """
        取得訊號的時序角色
        
        Args:
            signal_name (str): 訊號名稱
            
        Returns:
            str: 'clock', 'reset', 'enable', 'data', 'unknown'
        """
        if signal_name in self.clock_signals:
            return 'clock'
        elif signal_name in self.reset_signals:
            return 'reset'
        elif signal_name in self.posedge_signals or signal_name in self.negedge_signals:
            return 'enable'
        else:
            return 'data'


def integrate_clock_reset_detection(parsed_data, ast_root):
    """
    將時脈/重置偵測結果整合到已解析的資料結構中
    
    Args:
        parsed_data (dict): hw_stage1_parser.py 產生的解析資料
        ast_root: PyVerilog AST 根節點
        
    Returns:
        dict: 增強後的解析資料 (包含時序控制資訊)
    """
    detector = ClockResetDetector()
    timing_info = detector.analyze(ast_root)
    
    # 將時序資訊加入每個變數節點
    if 'variables' in parsed_data:
        for var_id, var_data in parsed_data['variables'].items():
            signal_name = var_data.get('name', var_id)
            attributes = detector.get_signal_attributes(signal_name)
            
            # 擴充變數資料
            var_data['is_clock'] = attributes['is_clock']
            var_data['is_reset'] = attributes['is_reset']
            var_data['timing_role'] = attributes['timing_role']
            
            # 為前端視覺化設定特殊顏色標記
            if attributes['is_clock']:
                var_data['highlight_color'] = '#FFD700'  # 亮黃色 (時脈)
            elif attributes['is_reset']:
                var_data['highlight_color'] = '#FF4444'  # 亮紅色 (重置)
    
    # 加入全域時序控制資訊
    parsed_data['timing_control'] = timing_info
    
    return parsed_data


# 使用範例
if __name__ == '__main__':
    """
    測試範例：偵測以下 Verilog 的時脈與重置訊號
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            counter <= 0;
        else
            counter <= counter + 1;
    end
    """
    from pyverilog.vparser.parser import parse
    
    test_verilog = """
    module test_module (
        input wire clk,
        input wire rst_n,
        output reg [7:0] counter
    );
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            counter <= 8'd0;
        else
            counter <= counter + 8'd1;
    end
    
    endmodule
    """
    
    # 解析 Verilog (需實際檔案路徑)
    # ast, _ = parse([test_file_path])
    # detector = ClockResetDetector()
    # result = detector.analyze(ast)
    # print('偵測到的時脈訊號:', result['clocks'])
    # print('偵測到的重置訊號:', result['resets'])
