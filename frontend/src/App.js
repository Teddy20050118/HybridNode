/**
 * HybridNode - Main Application Component
 * * 提供代碼依賴圖的互動式視覺化介面
 * 具備 C++ 軟體模式 (Qt Bridge) 與 Verilog 硬體模式 (React Flow)
 */

import React, { useState, useEffect, useCallback } from 'react';
import styled from 'styled-components';
import GraphComponent from './components/GraphComponent';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import StatsPanel from './components/StatsPanel';
import HardwareGraph from './components/HardwareGraph'; // [新增] 引入硬體圖表組件
import { useBridge } from './hooks/useBridge';

// --- 樣式組件 ---
const AppContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: #0d1117;
  color: #c9d1d9;
  overflow: hidden;
  position: relative;
`;

const MainContent = styled.div`
  display: flex;
  flex: 1;
  overflow: hidden;
`;

const GraphContainer = styled.div`
  flex: 1;
  position: relative;
  overflow: hidden;
`;

const LoadingOverlay = styled.div`
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(13, 17, 23, 0.95);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 9999;
`;

const LoadingSpinner = styled.div`
  border: 4px solid rgba(56, 139, 253, 0.1);
  border-top-color: #388bfd;
  border-radius: 50%;
  width: 50px;
  height: 50px;
  animation: spin 1s linear infinite;
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
`;

const LoadingText = styled.div`
  margin-top: 20px;
  font-size: 16px;
  color: #8b949e;
`;

const ErrorMessage = styled.div`
  padding: 20px;
  margin: 20px;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid #f85149;
  border-radius: 6px;
  color: #f85149;
  text-align: center;
`;

const EmptyState = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8b949e;
  font-size: 16px;
  gap: 12px;
`;

// 修改模式切換按鈕樣式，移到右下角避免被 Header 蓋住
const ModeToggleBtn = styled.button`
  position: absolute;
  bottom: 30px; /* 從 top 改成 bottom */
  right: 30px;  /* 稍微往內縮一點 */
  z-index: 10000;
  background: #1f6feb;
  color: white;
  border: 1px solid rgba(240, 246, 252, 0.1);
  padding: 12px 24px;
  border-radius: 50px; /* 改成圓角藥丸形狀，看起來更像懸浮按鈕 */
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.5);
  transition: all 0.2s;
  
  &:hover {
    background: #388bfd;
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.6);
  }
`;

function App() {
  // [新增] 軟硬體模式狀態 (預設開啟硬體模式方便測試)
  const [isHardwareMode, setIsHardwareMode] = useState(true);

  // 使用 Bridge Hook
  const {
    isReady,
    graphData: bridgeGraphData,
    stats: bridgeStats,
    progress,
    error: bridgeError,
    loading: bridgeLoading,
    loadExistingGraph,
    reloadProject,
    openDirectoryDialog,
  } = useBridge();

  // 本地狀態管理
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterMinRisk, setFilterMinRisk] = useState(0);
  const [showAllNodes, setShowAllNodes] = useState(false);
  const [highlightedNodes, setHighlightedNodes] = useState(new Set());
  const [filteredGraphData, setFilteredGraphData] = useState(null);

  const graphData = filteredGraphData || bridgeGraphData;
  const stats = bridgeStats;
  const loading = bridgeLoading;
  const error = bridgeError;

  // 應用風險過濾
  useEffect(() => {
    if (!bridgeGraphData || showAllNodes || filterMinRisk === 0) {
      setFilteredGraphData(null);
      return;
    }
    const filteredNodes = bridgeGraphData.nodes.filter(
      node => node.risk_score >= filterMinRisk
    );
    const nodeIds = new Set(filteredNodes.map(n => n.id));
    const filteredLinks = bridgeGraphData.links.filter(
      link => nodeIds.has(typeof link.source === 'object' ? link.source.id : link.source) && 
              nodeIds.has(typeof link.target === 'object' ? link.target.id : link.target)
    );
    setFilteredGraphData({
      nodes: filteredNodes,
      links: filteredLinks,
      stats: {
        ...bridgeGraphData.stats,
        total_nodes: filteredNodes.length,
        total_links: filteredLinks.length,
      }
    });
  }, [bridgeGraphData, filterMinRisk, showAllNodes]);

  const loadNodeDetails = useCallback((nodeId) => {
    if (!graphData) return;
    const node = graphData.nodes.find(n => n.id === nodeId);
    if (node) {
      const neighborsOut = [];
      const neighborsIn = [];
      graphData.links.forEach(link => {
        if (link.source === nodeId || link.source.id === nodeId) {
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          const targetNode = graphData.nodes.find(n => n.id === targetId);
          if (targetNode) neighborsOut.push({ id: targetNode.id, name: targetNode.name, dependency: link.dependency || 'call' });
        }
        if (link.target === nodeId || link.target.id === nodeId) {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const sourceNode = graphData.nodes.find(n => n.id === sourceId);
          if (sourceNode) neighborsIn.push({ id: sourceNode.id, name: sourceNode.name, dependency: link.dependency || 'call' });
        }
      });
      setSelectedNode({ ...node, neighbors_out: neighborsOut, neighbors_in: neighborsIn });
    }
  }, [graphData]);

  const handleNodeClick = useCallback((node) => {
    if (node) loadNodeDetails(node.id);
    else setSelectedNode(null);
  }, [loadNodeDetails]);

  const handleSearch = useCallback((query) => {
    setSearchQuery(query);
    if (!query || !graphData) {
      setHighlightedNodes(new Set());
      return;
    }
    const lowerQuery = query.toLowerCase();
    const matchedNodes = graphData.nodes
      .filter(node => node.name.toLowerCase().includes(lowerQuery) || node.id.toLowerCase().includes(lowerQuery))
      .map(node => node.id);
    setHighlightedNodes(new Set(matchedNodes));
    if (matchedNodes.length === 1) {
      const node = graphData.nodes.find(n => n.id === matchedNodes[0]);
      handleNodeClick(node);
    }
  }, [graphData, handleNodeClick]);

  const handleReload = useCallback(() => reloadProject(), [reloadProject]);
  const handleOpenProject = useCallback(() => openDirectoryDialog(), [openDirectoryDialog]);

  useEffect(() => {
    if (isReady && !graphData) {
      loadExistingGraph('output/graph_data.pt');
    }
  }, [isReady, graphData, loadExistingGraph]);

  return (
    <AppContainer>
      {/* 模式切換按鈕 */}
      <ModeToggleBtn onClick={() => setIsHardwareMode(!isHardwareMode)}>
        切換至：{isHardwareMode ? ' C++ 軟體模式' : ' Verilog 硬體模式'}
      </ModeToggleBtn>

      {isHardwareMode ? (
        /* =========================================
           硬體模式視圖 (React Flow)
           ========================================= */
        <HardwareGraph />
      ) : (
        /* =========================================
           軟體模式視圖 (Force Graph + Qt Bridge)
           ========================================= */
        <>
          <Header
            searchQuery={searchQuery}
            onSearch={handleSearch}
            filterMinRisk={filterMinRisk}
            onFilterChange={setFilterMinRisk}
            showAllNodes={showAllNodes}
            onToggleShowAll={() => setShowAllNodes(v => !v)}
            onReload={handleReload}
            onOpenProject={handleOpenProject}
            stats={stats}
          />

          {!isReady && !error && (
            <LoadingOverlay>
              <LoadingSpinner />
              <LoadingText>
                [CONNECTING] 正在透過 QWebChannel 連接 Python 後端...
              </LoadingText>
            </LoadingOverlay>
          )}

          {loading && isReady && (
            <LoadingOverlay>
              <LoadingSpinner />
              <LoadingText>
                {progress.message || 'Loading graph data...'}
                {progress.percentage > 0 && ` (${progress.percentage}%)`}
              </LoadingText>
            </LoadingOverlay>
          )}

          {error && !loading && (
            <ErrorMessage>
              <strong>Error:</strong> {error}
              <br />
              <button onClick={handleReload} style={{ marginTop: '10px', marginRight: '10px', padding: '8px 16px', background: '#238636', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>Retry</button>
              <button onClick={handleOpenProject} style={{ marginTop: '10px', padding: '8px 16px', background: '#1f6feb', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>Open Project</button>
            </ErrorMessage>
          )}

          {!loading && !error && graphData && graphData.nodes && graphData.nodes.length === 0 && (
            <MainContent>
              <EmptyState>
                <div style={{ fontSize: 48, opacity: 0.3 }}>( )</div>
                <div>[INFO] 未找到現有圖資料</div>
                <div style={{ fontSize: 13 }}>請點擊「 Open Project 」選擇專案目錄開始分析</div>
              </EmptyState>
            </MainContent>
          )}

          {!loading && !error && graphData && graphData.nodes && graphData.nodes.length > 0 && (
            <MainContent>
              <StatsPanel stats={stats} />
              <GraphContainer>
                <GraphComponent
                  data={graphData}
                  selectedNode={selectedNode}
                  highlightedNodes={highlightedNodes}
                  onNodeClick={handleNodeClick}
                />
              </GraphContainer>
              <Sidebar node={selectedNode} onClose={() => setSelectedNode(null)} />
            </MainContent>
          )}
        </>
      )}
    </AppContainer>
  );
}

export default App;