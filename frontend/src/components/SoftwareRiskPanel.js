import React, { useState, useCallback } from 'react';

/**
 * C++ 軟體模式 AI 風險預測分析面板
 *
 * 功能：
 * 1. 觸發後端 GNN + 危險函式標籤分析
 * 2. 顯示函式風險清單（由高至低排列）
 * 3. 點擊函式時高亮該函式節點與其呼叫鏈
 */
const SoftwareRiskPanel = ({ bridge, onSelectFunction, onClose }) => {
  const [results, setResults] = useState(null);
  const [summary, setSummary] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [expandedNodeId, setExpandedNodeId] = useState(null);

  const handleAnalyze = useCallback(() => {
    setIsAnalyzing(true);
    setError(null);
    setResults(null);
    setSummary(null);

    const config = JSON.stringify({
      graph_path: 'output/graph_data.pt'
    });

    if (bridge) {
      try {
        bridge.run_cpp_risk_analysis(config, (resultStr) => {
          try {
            const response = JSON.parse(resultStr);
            if (response.success) {
              setResults(response.results || []);
              setSummary(response.summary || null);
            } else {
              setError(response.error || '分析失敗');
            }
          } catch (e) {
            setError('解析回應失敗: ' + e.message);
          }
          setIsAnalyzing(false);
        });
      } catch (e) {
        setError('Bridge 呼叫失敗: ' + e.message);
        setIsAnalyzing(false);
      }
    } else {
      setError('Bridge 未連接，請確認應用程式在 PyQt6 桌面環境中執行');
      setIsAnalyzing(false);
    }
  }, [bridge]);

  const handleFunctionClick = useCallback((item) => {
    setSelectedNodeId(item.node_id);
    setExpandedNodeId(prev => prev === item.node_id ? null : item.node_id);
    if (onSelectFunction) {
      // 傳送此函式的 node_id 以及所有呼叫鏈節點 ID
      const allNodeIds = new Set([item.node_id]);
      if (item.call_chains) {
        item.call_chains.forEach(chain => {
          chain.forEach(nid => allNodeIds.add(nid));
        });
      }
      onSelectFunction(Array.from(allNodeIds), item);
    }
  }, [onSelectFunction]);

  const riskLevelColor = (level) => {
    switch (level) {
      case 'high': return '#ff4444';
      case 'medium': return '#ffaa00';
      case 'low': return '#44cc44';
      default: return '#888';
    }
  };

  const riskLevelLabel = (level) => {
    switch (level) {
      case 'high': return '高風險';
      case 'medium': return '中風險';
      case 'low': return '低風險';
      default: return '未知';
    }
  };

  // 只顯示中高風險的函式（low 太多會佔滿畫面）
  const displayResults = results
    ? results.filter(r => r.risk_score > 0)
    : null;

  return (
    <div style={{
      position: 'absolute',
      top: '60px',
      right: '20px',
      width: '440px',
      maxHeight: 'calc(100vh - 100px)',
      background: 'rgba(20, 22, 30, 0.97)',
      border: '1px solid #444',
      borderRadius: '12px',
      zIndex: 2000,
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'Consolas, monospace',
      boxShadow: '0 8px 32px rgba(0,0,0,0.5)'
    }}>
      {/* 標題列 */}
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid #333',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <span style={{ color: '#58a6ff', fontWeight: '700', fontSize: '15px' }}>
          AI 函式風險預測
        </span>
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,68,68,0.8)',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            padding: '4px 10px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: '600'
          }}
        >
          關閉
        </button>
      </div>

      {/* 說明與按鈕 */}
      <div style={{ padding: '14px 18px', borderBottom: '1px solid #333' }}>
        <div style={{ color: '#aaa', fontSize: '12px', marginBottom: '10px', lineHeight: '1.6' }}>
          結合 GNN 模型與危險函式標籤，分析可能造成專案錯誤的函式及其風險呼叫鏈。
        </div>
        <button
          onClick={handleAnalyze}
          disabled={isAnalyzing}
          style={{
            width: '100%',
            padding: '10px',
            background: isAnalyzing
              ? '#555'
              : 'linear-gradient(135deg, #58a6ff 0%, #1f6feb 100%)',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            cursor: isAnalyzing ? 'not-allowed' : 'pointer',
            fontSize: '13px',
            fontWeight: '600'
          }}
        >
          {isAnalyzing ? '分析中...' : '開始 AI 風險分析'}
        </button>
      </div>

      {/* 錯誤訊息 */}
      {error && (
        <div style={{ padding: '10px 18px', color: '#ff6666', fontSize: '12px', borderBottom: '1px solid #333' }}>
          {error}
        </div>
      )}

      {/* 分析摘要 */}
      {summary && (
        <div style={{
          padding: '12px 18px',
          borderBottom: '1px solid #333',
          display: 'flex',
          gap: '10px',
          flexWrap: 'wrap',
          alignItems: 'center'
        }}>
          <div style={{ color: '#aaa', fontSize: '11px', width: '100%', marginBottom: '4px' }}>
            分析摘要 — 共 {summary.total_functions} 個函式
            {summary.has_gnn_model ? ' (含 GNN 模型)' : ' (啟發式規則)'}
          </div>
          <span style={{
            background: 'rgba(255,68,68,0.2)',
            color: '#ff4444',
            padding: '4px 10px',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: '600'
          }}>
            高風險: {summary.high}
          </span>
          <span style={{
            background: 'rgba(255,170,0,0.2)',
            color: '#ffaa00',
            padding: '4px 10px',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: '600'
          }}>
            中風險: {summary.medium}
          </span>
          <span style={{
            background: 'rgba(68,204,68,0.2)',
            color: '#44cc44',
            padding: '4px 10px',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: '600'
          }}>
            低風險: {summary.low}
          </span>
        </div>
      )}

      {/* 風險函式列表 */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '8px 0'
      }}>
        {displayResults && displayResults.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', color: '#888', fontSize: '13px' }}>
            所有函式風險均為零
          </div>
        )}

        {displayResults && displayResults.map((item, idx) => (
          <div
            key={item.node_id}
            onClick={() => handleFunctionClick(item)}
            style={{
              padding: '12px 18px',
              cursor: 'pointer',
              background: selectedNodeId === item.node_id
                ? 'rgba(88, 166, 255, 0.15)'
                : 'transparent',
              borderBottom: '1px solid #2a2a2a',
              transition: 'background 0.2s'
            }}
            onMouseEnter={e => {
              if (selectedNodeId !== item.node_id)
                e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
            }}
            onMouseLeave={e => {
              if (selectedNodeId !== item.node_id)
                e.currentTarget.style.background = 'transparent';
            }}
          >
            {/* 函式標題行 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <span style={{
                background: riskLevelColor(item.risk_level),
                color: item.risk_level === 'medium' ? '#000' : '#fff',
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '10px',
                fontWeight: '700',
                minWidth: '50px',
                textAlign: 'center'
              }}>
                {riskLevelLabel(item.risk_level)}
              </span>
              <span style={{
                color: '#ccc',
                fontSize: '11px',
                fontWeight: '600'
              }}>
                #{idx + 1} — {(item.risk_score * 100).toFixed(1)}%
              </span>
            </div>

            {/* 函式名稱 */}
            <div style={{
              color: '#e0e0e0',
              fontSize: '13px',
              fontWeight: '600',
              marginBottom: '4px'
            }}>
              {item.name}
            </div>

            {/* 度量資訊簡要 */}
            <div style={{
              color: '#777',
              fontSize: '10px',
              display: 'flex',
              gap: '10px'
            }}>
              <span>LOC: {item.metrics?.loc || 0}</span>
              <span>複雜度: {item.metrics?.complexity || 0}</span>
              <span>入度: {item.metrics?.in_degree || 0}</span>
              <span>出度: {item.metrics?.out_degree || 0}</span>
            </div>

            {/* 展開：風險原因與呼叫鏈 */}
            {expandedNodeId === item.node_id && (
              <div style={{
                marginTop: '10px',
                padding: '10px',
                background: 'rgba(0,0,0,0.3)',
                borderRadius: '6px',
                borderLeft: `3px solid ${riskLevelColor(item.risk_level)}`
              }}>
                {/* 風險原因 */}
                <div style={{ color: '#aaa', fontSize: '11px', marginBottom: '6px', fontWeight: '600' }}>
                  風險原因：
                </div>
                {item.reasons.map((reason, ri) => (
                  <div key={ri} style={{
                    color: '#ddd',
                    fontSize: '11px',
                    lineHeight: '1.6',
                    marginBottom: '4px',
                    paddingLeft: '10px'
                  }}>
                    • {reason}
                  </div>
                ))}

                {/* 風險呼叫鏈 */}
                {item.call_chain_strs && item.call_chain_strs.length > 0 && (
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ color: '#aaa', fontSize: '11px', marginBottom: '4px', fontWeight: '600' }}>
                      風險呼叫鏈：
                    </div>
                    {item.call_chain_strs.map((chain, ci) => (
                      <div key={ci} style={{
                        color: '#ff9966',
                        fontSize: '11px',
                        lineHeight: '1.6',
                        paddingLeft: '10px',
                        marginBottom: '2px'
                      }}>
                        {chain}
                      </div>
                    ))}
                  </div>
                )}

                {/* 詳細分數 */}
                {item.detail_scores && (
                  <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {Object.entries(item.detail_scores).map(([key, val]) => (
                      <span key={key} style={{
                        background: 'rgba(88,166,255,0.15)',
                        color: '#8899bb',
                        padding: '2px 6px',
                        borderRadius: '3px',
                        fontSize: '10px'
                      }}>
                        {key}: {(val * 100).toFixed(0)}%
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default SoftwareRiskPanel;
