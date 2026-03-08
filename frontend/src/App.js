/**
 * HybridNode - Main Application Component
 * 
 * 提供代碼依賴圖的互動式視覺化介面
 * 使用 QWebChannel 與 Python 後端通信（無需網路請求）
 */

import React, { useState, useEffect, useCallback } from 'react';
import styled from 'styled-components';
import GraphComponent from './components/GraphComponent';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import StatsPanel from './components/StatsPanel';
import { useBridge } from './hooks/useBridge';

// 樣式組件
const AppContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: #0d1117;
  color: #c9d1d9;
  overflow: hidden;
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
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
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

// [INFO] 當 load_existing_graph 回傳空狀態（檔案不存在）時顯示此元件
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

function App() {
  // 使用 Bridge Hook（替代 axios）
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
  // 預設為 false，確保 Min Risk 滑桿在初始狀態下可互動
  const [showAllNodes, setShowAllNodes] = useState(false);
  const [highlightedNodes, setHighlightedNodes] = useState(new Set());
  const [filteredGraphData, setFilteredGraphData] = useState(null);

  // 統一的狀態（來自 Bridge）
  const graphData = filteredGraphData || bridgeGraphData;
  const stats = bridgeStats;
  const loading = bridgeLoading;
  const error = bridgeError;

  /**
   * 應用風險過濾（用戶端過濾）
   */
  useEffect(() => {
    // showAllNodes 開啟時展示全部節點，不管風險分數
    if (!bridgeGraphData || showAllNodes || filterMinRisk === 0) {
      setFilteredGraphData(null);
      return;
    }

    console.log(`[FILTER] 過濾風險分數 < ${filterMinRisk} 的節點`);

    // 過濾節點
    const filteredNodes = bridgeGraphData.nodes.filter(
      node => node.risk_score >= filterMinRisk
    );

    // 重新計算連接
    const nodeIds = new Set(filteredNodes.map(n => n.id));
    const filteredLinks = bridgeGraphData.links.filter(
      link => nodeIds.has(
        typeof link.source === 'object' ? link.source.id : link.source
      ) && nodeIds.has(
        typeof link.target === 'object' ? link.target.id : link.target
      )
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

  /**
   * 載入節點詳細信息（從本地圖數據）
   */
  const loadNodeDetails = useCallback((nodeId) => {
    if (!graphData) return;

    const node = graphData.nodes.find(n => n.id === nodeId);
    if (node) {
      // 添加鄰居信息
      const neighborsOut = [];
      const neighborsIn = [];

      graphData.links.forEach(link => {
        if (link.source === nodeId || link.source.id === nodeId) {
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;
          const targetNode = graphData.nodes.find(n => n.id === targetId);
          if (targetNode) {
            neighborsOut.push({
              id: targetNode.id,
              name: targetNode.name,
              dependency: link.dependency || 'call'
            });
          }
        }
        if (link.target === nodeId || link.target.id === nodeId) {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const sourceNode = graphData.nodes.find(n => n.id === sourceId);
          if (sourceNode) {
            neighborsIn.push({
              id: sourceNode.id,
              name: sourceNode.name,
              dependency: link.dependency || 'call'
            });
          }
        }
      });

      setSelectedNode({
        ...node,
        neighbors_out: neighborsOut,
        neighbors_in: neighborsIn,
      });
    }
  }, [graphData]);

  /**
   * 處理節點點擊事件
   */
  const handleNodeClick = useCallback((node) => {
    if (node) {
      loadNodeDetails(node.id);
    } else {
      setSelectedNode(null);
    }
  }, [loadNodeDetails]);

  /**
   * 處理搜尋
   */
  const handleSearch = useCallback((query) => {
    setSearchQuery(query);

    if (!query || !graphData) {
      setHighlightedNodes(new Set());
      return;
    }

    const lowerQuery = query.toLowerCase();
    const matchedNodes = graphData.nodes
      .filter(node =>
        node.name.toLowerCase().includes(lowerQuery) ||
        node.id.toLowerCase().includes(lowerQuery)
      )
      .map(node => node.id);

    setHighlightedNodes(new Set(matchedNodes));

    // 如果只有一個匹配，自動選中
    if (matchedNodes.length === 1) {
      const node = graphData.nodes.find(n => n.id === matchedNodes[0]);
      handleNodeClick(node);
    }
  }, [graphData, handleNodeClick]);

  /**
   * 重新載入數據（從現有文件）
   */
  const handleReload = useCallback(() => {
    console.log('[RELOAD] 觸發重新分析（優先使用已選擇的專案路徑）...');
    reloadProject();
  }, [reloadProject]);

  /**
   * 打開文件夾選擇對話框
   */
  const handleOpenProject = useCallback(() => {
    console.log('[DIALOG] Opening project selection dialog...');
    openDirectoryDialog();
  }, [openDirectoryDialog]);

  // 初始化時自動載入現有圖數據（如果存在）
  useEffect(() => {
    if (isReady && !graphData) {
      console.log('[AUTO] Auto-loading existing graph data...');
      // loadExistingGraph 使用信号模式，不返回 Promise
      // 错误通过 analysisError 信号处理
      loadExistingGraph('output/graph_data.pt');
    }
  }, [isReady, graphData, loadExistingGraph]);

  // 大圖效能警告
  useEffect(() => {
    if (stats && stats.total_nodes > 500) {
      console.warn(
        `[WARN] 效能警告：圖包含 ${stats.total_nodes} 個節點，` +
        `建議啟用 cooldownTicks 將其設為 ${Math.min(100, stats.total_nodes / 5)}`
      );
    }
  }, [stats]);

  return (
    <AppContainer>
      {/* 頂部導航欄 */}
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

      {/* 接連待機 */}
      {!isReady && !error && (
        <LoadingOverlay>
          <LoadingSpinner />
          <LoadingText>
            [CONNECTING] 正在透過 QWebChannel 連接 Python 後端...
            <br />
            <small style={{ fontSize: '12px', marginTop: '10px', display: 'block', opacity: 0.7 }}>
              {typeof window !== 'undefined' && typeof qt !== 'undefined'
                ? 'Qt 已偵測，正在建立通道...'
                : '等待 Qt WebChannel 傳輸層...'}
            </small>
          </LoadingText>
        </LoadingOverlay>
      )}

      {/* 載入/分析中遮罩 */}
      {loading && isReady && (
        <LoadingOverlay>
          <LoadingSpinner />
          <LoadingText>
            {progress.message || 'Loading graph data...'}
            {progress.percentage > 0 && ` (${progress.percentage}%)`}
          </LoadingText>
        </LoadingOverlay>
      )}

      {/* 錯誤信息 */}
      {error && !loading && (
        <ErrorMessage>
          <strong>Error:</strong> {error}
          <br />
          <button
            onClick={handleReload}
            style={{
              marginTop: '10px',
              marginRight: '10px',
              padding: '8px 16px',
              background: '#238636',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer'
            }}
          >
            Retry Load Existing
          </button>
          <button
            onClick={handleOpenProject}
            style={{
              marginTop: '10px',
              padding: '8px 16px',
              background: '#1f6feb',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer'
            }}
          >
            Open Project
          </button>
        </ErrorMessage>
      )}

      {/* 空狀態：檔案不存在，等待使用者開启新專案 */}
      {!loading && !error && graphData && graphData.nodes && graphData.nodes.length === 0 && (
        <MainContent>
          <EmptyState>
            <div style={{ fontSize: 48, opacity: 0.3 }}>( )</div>
            <div>[INFO] 未找到現有圖資料</div>
            <div style={{ fontSize: 13 }}>請點擊「 Open Project 」選擇 C++ 專案目錄開始分析</div>
          </EmptyState>
        </MainContent>
      )}

      {/* 主要內容區域 */}
      {!loading && !error && graphData && graphData.nodes && graphData.nodes.length > 0 && (
        <MainContent>
          {/* 統計面板（左側） */}
          <StatsPanel stats={stats} />

          {/* 圖表區域（中間） */}
          <GraphContainer>
            <GraphComponent
              data={graphData}
              selectedNode={selectedNode}
              highlightedNodes={highlightedNodes}
              onNodeClick={handleNodeClick}
            />
          </GraphContainer>

          {/* 側邊欄（右側） */}
          <Sidebar
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
          />
        </MainContent>
      )}
    </AppContainer>
  );
}

export default App;
