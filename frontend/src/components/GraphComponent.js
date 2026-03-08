/**
 * GraphComponent - 互動式力導向圖視覺化
 *
 * 核心修正：
 * 1. 使用 ResizeObserver 測量容器尺寸並明確傳入 width/height
 * 2. 移除 nodeCanvasObject，改用純函式 prop（nodeColor、nodeVal）
 * 3. zoomToFit 在 onEngineStop + 備用 timer 雙重觸發
 */

import React, { useRef, useEffect, useCallback, useMemo, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

// ── 顏色映射 ─────────────────────────────────────────────────────────────────
const getRiskColor = (score) => {
  const s = typeof score === 'number' ? score : 0;
  if (s >= 0.7) return '#ff4d4f';
  if (s >= 0.4) return '#faad14';
  return '#52c41a';
};

// ── 節點大小 ─────────────────────────────────────────────────────────────────
const calcNodeVal = (node) => {
  if (node.val && node.val > 0) return node.val;
  return Math.max(5, (node.in_degree || 0) * 2);
};

// ── Main Component ───────────────────────────────────────────────────────────
const GraphComponent = ({
  data,
  selectedNode,
  highlightedNodes = new Set(),
  onNodeClick,
}) => {
  const containerRef = useRef(null);
  const graphRef     = useRef(null);

  // 容器尺寸狀態
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // ── ResizeObserver：監聽容器大小 ─────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const measure = () => {
      const { clientWidth, clientHeight } = el;
      if (clientWidth > 0 && clientHeight > 0) {
        setDimensions({ width: clientWidth, height: clientHeight });
      }
    };

    measure(); // 初始量測

    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── zoomToFit helper ──────────────────────────────────────────────────────
  const doZoom = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoomToFit(500, 80);
    }
  }, []);

  // ── 資料更新時重新觸發 zoomToFit ─────────────────────────────────────────
  useEffect(() => {
    if (!data) return;
    // 等引擎穩定後執行（備用 timer）
    const t1 = setTimeout(doZoom, 800);
    const t2 = setTimeout(doZoom, 2000); // 雙保險
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [data, doZoom]);

  // ── 選中節點聚焦 ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (graphRef.current && selectedNode?.x != null) {
      graphRef.current.centerAt(selectedNode.x, selectedNode.y, 600);
      graphRef.current.zoom(3, 600);
    }
  }, [selectedNode]);

  // ── 節點顏色（函式 prop） ────────────────────────────────────────────────
  const nodeColor = useCallback((node) => {
    if (node.color && node.color.length > 0) return node.color;
    return getRiskColor(node.risk_score);
  }, []);

  // ── 節點大小（函式 prop） ────────────────────────────────────────────────
  const nodeVal = useCallback(calcNodeVal, []);

  // ── Tooltip HTML ─────────────────────────────────────────────────────────
  const nodeLabel = useCallback((node) => {
    const riskText = node.risk_label === 1 ? '[高風險]' : '[安全]';
    const pct = ((node.risk_score || 0) * 100).toFixed(0);
    return (
      `<div style="background:rgba(13,17,23,.95);padding:10px;border-radius:6px;` +
      `border:1px solid #30363d;font-size:13px;line-height:1.7;color:#c9d1d9">` +
      `<strong>${node.name || node.id}</strong><br/>` +
      `<span style="color:${getRiskColor(node.risk_score)}">${riskText} ${pct}%</span><br/>` +
      `類型: ${node.type || '-'} &nbsp; LOC: ${node.loc || 0}<br/>` +
      `入度: ${node.in_degree || 0} &nbsp; 出度: ${node.out_degree || 0}` +
      `</div>`
    );
  }, []);

  // ── 選中/高亮後的 canvas 疊加（純覆蓋光環，不干擾預設繪製） ─────────────
  const nodeCanvasObjectMode = useCallback(() => 'after', []);

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    if (node.x == null || node.y == null) return;

    const isSelected   = selectedNode && selectedNode.id === node.id;
    const isHighlighted = highlightedNodes.has(node.id);
    if (!isSelected && !isHighlighted) return;

    // 光環半徑：依 nodeVal 估算
    const r = Math.sqrt(calcNodeVal(node)) * 3 + 3;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = isSelected
      ? 'rgba(56,139,253,0.30)'
      : 'rgba(255,255,255,0.20)';
    ctx.fill();

    if (isSelected) {
      ctx.strokeStyle = '#388bfd';
      ctx.lineWidth   = 1.5 / globalScale;
      ctx.stroke();
    }

    // 縮放夠大時顯示標籤文字
    if (globalScale >= 1.5 || isSelected) {
      const label    = node.name || node.id || '';
      const fontSize = Math.max(10, 11 / globalScale);
      ctx.font          = `${fontSize}px Sans-Serif`;
      ctx.textAlign     = 'center';
      ctx.textBaseline  = 'top';
      const nodeR  = Math.sqrt(calcNodeVal(node)) * 2.5;
      const textY  = node.y + nodeR + 2;
      const tw     = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(13,17,23,0.75)';
      ctx.fillRect(node.x - tw / 2 - 2, textY - 1, tw + 4, fontSize + 2);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(label, node.x, textY);
    }
  }, [selectedNode, highlightedNodes]);

  // ── 連線樣式 ─────────────────────────────────────────────────────────────
  const linkColor = useCallback(
    () => 'rgba(139,148,158,0.5)',
    []
  );
  const linkWidth = useCallback(
    (link) => (link.dependency === 'call' ? 1.5 : 1),
    []
  );

  // ── cooldownTicks：有限值讓引擎能停止並觸發 onEngineStop ─────────────────
  const cooldownTicks = useMemo(() => {
    const n = data?.nodes?.length || 0;
    if (n > 500) return Math.floor(n / 5);
    if (n > 200) return 200;
    return 300;
  }, [data]);

  // ── 事件處理 ─────────────────────────────────────────────────────────────
  const handleNodeClick       = useCallback((node) => onNodeClick?.(node), [onNodeClick]);
  const handleBackgroundClick = useCallback(() => onNodeClick?.(null), [onNodeClick]);

  // ── 無資料時的 Placeholder ────────────────────────────────────────────────
  if (!data || !Array.isArray(data.nodes) || data.nodes.length === 0) {
    return (
      <div ref={containerRef} style={{ width: '100%', height: '100%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#8b949e', fontSize: '14px' }}>
        [INFO] 尚無圖形資料可顯示
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
      <ForceGraph2D
        ref={graphRef}
        graphData={data}

        // ── 明確傳入容器尺寸（關鍵：讓 D3 正確計算節點中心） ───────────────
        width={dimensions.width}
        height={dimensions.height}

        // ── 節點渲染（函式 prop，預設繪製圓圈） ─────────────────────────────
        nodeColor={nodeColor}
        nodeVal={nodeVal}
        nodeLabel={nodeLabel}
        nodeRelSize={4}

        // ── 選中/高亮疊加層 ──────────────────────────────────────────────
        nodeCanvasObject={nodeCanvasObject}
        nodeCanvasObjectMode={nodeCanvasObjectMode}

        // ── 點擊範圍 ────────────────────────────────────────────────────
        nodePointerAreaPaint={(node, hitColor, ctx) => {
          if (node.x == null) return;
          const r = Math.sqrt(calcNodeVal(node)) * 4 + 2;
          ctx.fillStyle = hitColor;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.fill();
        }}

        // ── 連線 ────────────────────────────────────────────────────────
        linkColor={linkColor}
        linkWidth={linkWidth}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.003}

        // ── 力學模擬 ────────────────────────────────────────────────────
        cooldownTicks={cooldownTicks}
        warmupTicks={30}
        d3AlphaDecay={0.03}
        d3VelocityDecay={0.4}
        onEngineStop={doZoom}

        // ── 互動 ────────────────────────────────────────────────────────
        onNodeClick={handleNodeClick}
        onBackgroundClick={handleBackgroundClick}
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}

        // ── 背景 ────────────────────────────────────────────────────────
        backgroundColor="#0d1117"
      />
    </div>
  );
};

export default GraphComponent;
