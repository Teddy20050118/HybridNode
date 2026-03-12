import React, { useMemo, useRef, useEffect, useState } from 'react';
import { getBezierPath, EdgeLabelRenderer, BaseEdge } from 'reactflow';

/**
 * 自定義硬體連線元件 - 支援正交路徑與即時邏輯值標記
 * 
 * 功能特性:
 * 1. 正交路徑佈局 (Manhattan Routing)
 * 2. 動態邏輯值標籤 (0/1/Bus)
 * 3. 時脈/重置訊號高亮
 * 4. 滑鼠懸停路徑追蹤
 */
const CustomHardwareEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
  style = {}
}) => {
  
  // 計算正交路徑 (Manhattan Routing)
  const orthogonalPath = useMemo(() => {
    return calculateOrthogonalPath(sourceX, sourceY, targetX, targetY);
  }, [sourceX, sourceY, targetX, targetY]);

  // 取得即時邏輯值
  const currentValue = data?.currentValue;
  const signalType = data?.signalType; // 'clock', 'reset', 'data'
  const busWidth = data?.busWidth || 1;
  const radix = data?.radix || 'bin'; // 'bin', 'hex', 'dec'

  // 根據訊號類型設定顏色與樣式
  const edgeStyle = useMemo(() => {
    let color = '#888';
    let width = 2;
    let animated = false;

    if (signalType === 'clock') {
      // 時脈訊號：亮黃色 + 脈衝動畫
      color = '#FFD700';
      width = 3;
      animated = true;
    } else if (signalType === 'reset') {
      // 重置訊號：亮紅色 + 加粗
      color = '#FF4444';
      width = 3;
      animated = false;
    } else if (currentValue !== undefined) {
      // 資料訊號：根據邏輯值著色
      if (currentValue === '1' || (typeof currentValue === 'string' && currentValue.includes('1'))) {
        color = '#00FF00'; // 高電位：綠色
        animated = true;
      } else if (currentValue === '0') {
        color = '#444444'; // 低電位：暗灰色
        animated = false;
      } else {
        color = '#FF6600'; // 未知狀態 (x/z)：橘色
        animated = false;
      }
    }

    return {
      stroke: color,
      strokeWidth: width,
      ...style
    };
  }, [signalType, currentValue, style]);

  // 計算標籤位置 (連線中點)
  const labelPosition = useMemo(() => {
    return {
      x: (sourceX + targetX) / 2,
      y: (sourceY + targetY) / 2
    };
  }, [sourceX, sourceY, targetX, targetY]);

  // 格式化顯示值
  const formattedValue = useMemo(() => {
    if (currentValue === undefined) return null;

    if (busWidth === 1) {
      return `1'b${currentValue}`;
    } else {
      // 多位元 Bus 顯示
      if (radix === 'hex') {
        const hexValue = parseInt(currentValue.replace(/[xz]/g, '0'), 2).toString(16).toUpperCase();
        return `${busWidth}'h${hexValue}`;
      } else if (radix === 'dec') {
        const decValue = parseInt(currentValue.replace(/[xz]/g, '0'), 2);
        return `${busWidth}'d${decValue}`;
      } else {
        return `${busWidth}'b${currentValue}`;
      }
    }
  }, [currentValue, busWidth, radix]);

  // ===== 值變化閃爍動畫 =====
  const prevValRef = useRef(currentValue);
  const [isFlashing, setIsFlashing] = useState(false);

  useEffect(() => {
    if (prevValRef.current !== undefined && currentValue !== prevValRef.current) {
      setIsFlashing(true);
      const timer = setTimeout(() => setIsFlashing(false), 400);
      prevValRef.current = currentValue;
      return () => clearTimeout(timer);
    }
    prevValRef.current = currentValue;
  }, [currentValue]);

  // 閃爍時加寬 + 白色高光
  const flashStyle = isFlashing ? { 
    strokeWidth: (edgeStyle.strokeWidth || 2) + 2,
    filter: 'drop-shadow(0 0 6px #fff)'
  } : {};

  const finalEdgeStyle = { ...edgeStyle, ...flashStyle };

  return (
    <>
      {/* 主要連線路徑 */}
      <BaseEdge
        id={id}
        path={orthogonalPath}
        markerEnd={markerEnd}
        style={finalEdgeStyle}
      />

      {/* 動態邏輯值標籤 */}
      {formattedValue && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelPosition.x}px, ${labelPosition.y}px)`,
              background: 'rgba(0, 0, 0, 0.85)',
              padding: '4px 8px',
              borderRadius: '4px',
              fontSize: '11px',
              fontWeight: 'bold',
              color: edgeStyle.stroke,
              border: `1px solid ${edgeStyle.stroke}`,
              pointerEvents: 'none',
              fontFamily: 'Consolas, monospace',
              whiteSpace: 'nowrap',
              zIndex: 1000
            }}
            className="nodrag nopan"
          >
            {formattedValue}
          </div>
        </EdgeLabelRenderer>
      )}

      {/* 時脈訊號特殊標記 */}
      {signalType === 'clock' && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelPosition.x}px, ${labelPosition.y - 20}px)`,
              background: '#FFD700',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '9px',
              fontWeight: 'bold',
              color: '#000',
              pointerEvents: 'none',
              fontFamily: 'Consolas, monospace'
            }}
            className="nodrag nopan"
          >
            CLK
          </div>
        </EdgeLabelRenderer>
      )}

      {/* 重置訊號特殊標記 */}
      {signalType === 'reset' && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelPosition.x}px, ${labelPosition.y - 20}px)`,
              background: '#FF4444',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '9px',
              fontWeight: 'bold',
              color: '#FFF',
              pointerEvents: 'none',
              fontFamily: 'Consolas, monospace'
            }}
            className="nodrag nopan"
          >
            RST
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

/**
 * 計算正交路徑 (Manhattan Routing)
 * 
 * 實作簡化版的曼哈頓路徑演算法，確保連線只有水平與垂直線段
 * 
 * @param {number} x1 - 起點 X 座標
 * @param {number} y1 - 起點 Y 座標
 * @param {number} x2 - 終點 X 座標
 * @param {number} y2 - 終點 Y 座標
 * @returns {string} SVG path 字串
 */
function calculateOrthogonalPath(x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;

  // 計算中間轉折點
  // 策略：先水平移動一半距離，再垂直移動，最後水平移動剩餘距離
  const midX = x1 + dx / 2;

  // 建構 SVG path
  // M: 移動到起點
  // L: 繪製直線到指定點
  const path = `
    M ${x1},${y1}
    L ${midX},${y1}
    L ${midX},${y2}
    L ${x2},${y2}
  `;

  return path.trim();
}

/**
 * 進階正交路徑演算法 - 避開障礙物
 * 
 * 此函式預留給未來擴展，實作 A* 或 Lee's Algorithm
 * 可避開中間的節點障礙物
 */
function calculateAdvancedOrthogonalPath(x1, y1, x2, y2, obstacles = []) {
  // TODO: 實作 A* 路徑搜尋演算法
  // 目前先使用基本版本
  return calculateOrthogonalPath(x1, y1, x2, y2);
}

/**
 * 路徑高亮追蹤 Hook
 * 
 * 當滑鼠懸停在連線或節點上時，向前後追蹤整條資料路徑
 * 
 * 使用方式:
 *   const { highlightedPath, onEdgeHover } = usePathHighlight();
 */
export const usePathHighlight = () => {
  const [highlightedPath, setHighlightedPath] = React.useState(new Set());

  const onEdgeHover = React.useCallback((edgeId, edges, nodes) => {
    // 向前追蹤：找出所有驅動此連線的路徑
    const forwardPath = new Set();
    const backwardPath = new Set();

    const currentEdge = edges.find(e => e.id === edgeId);
    if (!currentEdge) return;

    // 遞迴追蹤來源
    const traceBackward = (nodeId) => {
      const incomingEdges = edges.filter(e => e.target === nodeId);
      incomingEdges.forEach(edge => {
        backwardPath.add(edge.id);
        traceBackward(edge.source);
      });
    };

    // 遞迴追蹤目標
    const traceForward = (nodeId) => {
      const outgoingEdges = edges.filter(e => e.source === nodeId);
      outgoingEdges.forEach(edge => {
        forwardPath.add(edge.id);
        traceForward(edge.target);
      });
    };

    traceBackward(currentEdge.source);
    traceForward(currentEdge.target);

    const fullPath = new Set([...backwardPath, ...forwardPath, edgeId]);
    setHighlightedPath(fullPath);
  }, []);

  const onEdgeLeave = React.useCallback(() => {
    setHighlightedPath(new Set());
  }, []);

  return { highlightedPath, onEdgeHover, onEdgeLeave };
};

export default CustomHardwareEdge;
