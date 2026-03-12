import React, { useRef, useEffect, useState } from 'react';
import { Handle, Position } from 'reactflow';

const HardwareNode = ({ data }) => {
  // 硬體類型視覺化：區分變數節點與子模組實例
  const isSeq = data.type === 'reg' || data.type === 'input';
  const isSubmodule = data.type === 'submodule';
  
  // 設定背景色：
  // - 子模組實例：深灰色大方塊 (視覺層級最高)
  // - SEQ 節點 (reg, input)：粉紅色
  // - COM 節點 (wire, output)：淺綠色
  let bgColor = '#ccffcc'; 
  if (isSeq) bgColor = '#ffcccc';
  if (isSubmodule) bgColor = '#666666'; // 子模組使用深灰色

  // 設定形狀與尺寸：
  // - 子模組：方形，較大尺寸 (180px x 90px)
  // - 變數節點：較小尺寸 (120px x 50px)
  const borderRadius = (isSeq || isSubmodule) ? '8px' : '20px'; 
  const minWidth = isSubmodule ? '180px' : '120px';
  const minHeight = isSubmodule ? '90px' : '50px';
  const padding = isSubmodule ? '16px 24px' : '12px 20px';
  const fontSize = isSubmodule ? '16px' : '14px';
  const textColor = isSubmodule ? '#ffffff' : '#000000'; // 子模組用白字

  // 風險警告樣式 — unused 使用黃色邊框，其他風險使用紅色邊框
  const hasRisk = !!data.risk;
  const isUnusedOnly = hasRisk && data.risk === 'unused';
  
  let borderStyle, boxShadow;
  if (isUnusedOnly) {
    borderStyle = '3px solid #FFD700';
    boxShadow = '0 0 12px rgba(255, 215, 0, 0.6)';
  } else if (hasRisk) {
    borderStyle = '3px solid #ff0000';
    boxShadow = '0 0 15px rgba(255, 0, 0, 0.8)';
  } else if (isSubmodule) {
    borderStyle = '2px solid #444';
    boxShadow = '0 6px 20px rgba(0,0,0,0.4)';
  } else {
    borderStyle = '1px solid #333';
    boxShadow = '3px 3px 5px rgba(0,0,0,0.1)';
  }

  // 動態電位值狀態
  const hasCurrentValue = data.currentValue !== undefined;

  // ===== 值變化閃爍動畫 =====
  const prevValueRef = useRef(data.currentValue);
  const [isFlashing, setIsFlashing] = useState(false);

  useEffect(() => {
    if (prevValueRef.current !== undefined && data.currentValue !== prevValueRef.current) {
      setIsFlashing(true);
      const timer = setTimeout(() => setIsFlashing(false), 400);
      prevValueRef.current = data.currentValue;
      return () => clearTimeout(timer);
    }
    prevValueRef.current = data.currentValue;
  }, [data.currentValue]);

  // 閃爍時覆蓋背景色
  const effectiveBg = isFlashing && !isSubmodule ? '#ffffaa' : bgColor;

  return (
    <div style={{
      padding: padding,
      background: effectiveBg,
      borderRadius: borderRadius,
      border: borderStyle,
      boxShadow: boxShadow,
      textAlign: 'center',
      minWidth: minWidth,
      minHeight: minHeight,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      fontFamily: 'Consolas, monospace',
      transition: 'background 0.35s ease, border-color 0.35s ease, box-shadow 0.35s ease',
      cursor: isSubmodule ? 'pointer' : 'default', // 子模組可點擊
      position: 'relative'
    }}>
      {/* 左側輸入接點 */}
      <Handle type="target" position={Position.Left} style={{ background: '#555' }} />
      
      {/* 子模組實例專用提示 */}
      {isSubmodule && (
        <div style={{ 
          fontSize: '10px', 
          color: '#aaa', 
          marginBottom: '6px',
          letterSpacing: '1px'
        }}>
          實例化子模組
        </div>
      )}
      
      {/* 模組或變數名稱 */}
      <div style={{ fontWeight: 'bold', fontSize: fontSize, color: textColor }}>
        {data.label}
      </div>
      
      {/* 類型與位元寬度資訊（變數節點專用） */}
      {!isSubmodule && (
        <div style={{ fontSize: '10px', color: '#555', marginTop: '4px' }}>
          {data.type.toUpperCase()} {data.width > 1 ? `[${data.msb}:${data.lsb}]` : ''}
        </div>
      )}

      {/* 子模組類型提示（推斷出的模組定義名稱） */}
      {isSubmodule && (
        <div style={{ 
          fontSize: '11px', 
          color: '#ccc', 
          marginTop: '6px',
          fontStyle: 'italic'
        }}>
          雙擊展開內部結構
        </div>
      )}

      {/* 即時電位值顯示 (模擬模式) */}
      {hasCurrentValue && !isSubmodule && (
        <div style={{ 
          fontSize: '11px', 
          color: '#ffffff', 
          background: '#0066cc', 
          marginTop: '8px', 
          padding: '4px 6px', 
          borderRadius: '4px', 
          fontWeight: 'bold',
          letterSpacing: '0.5px'
        }}>
          VAL: {data.currentValue}
        </div>
      )}

      {/* 警告標籤顯示 */}
      {hasRisk && (
        <div style={{ 
          fontSize: '10px', color: isUnusedOnly ? '#000' : 'white', 
          background: isUnusedOnly ? '#FFD700' : '#d32f2f', 
          marginTop: '6px', padding: '3px 4px', borderRadius: '4px', fontWeight: 'bold' 
        }}>
          {isUnusedOnly ? '⚠ 未使用' : `警告: ${data.risk}`}
        </div>
      )}

      {/* 右側輸出接點 */}
      <Handle type="source" position={Position.Right} style={{ background: '#555' }} />
    </div>
  );
};

export default HardwareNode;