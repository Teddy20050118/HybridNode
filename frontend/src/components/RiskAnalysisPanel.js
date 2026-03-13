import React, { useState, useCallback } from 'react';

/**
 * AI 風險預測分析面板
 *
 * 功能：
 * 1. 使用者輸入電路功能描述
 * 2. 觸發後端 AI 分析
 * 3. 顯示風險路徑清單（由高至低排列）
 * 4. 點擊路徑時回傳路徑節點 ID 供圖形高亮
 */
const RiskAnalysisPanel = ({ bridge, onSelectPath, onClose }) => {
  const [description, setDescription] = useState('');
  const [results, setResults] = useState(null);
  const [summary, setSummary] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const [selectedPathId, setSelectedPathId] = useState(null);
  const [expandedPathId, setExpandedPathId] = useState(null);

  const handleAnalyze = useCallback(() => {
    if (!description.trim()) {
      setError('請輸入電路功能描述');
      return;
    }
    setIsAnalyzing(true);
    setError(null);
    setResults(null);
    setSummary(null);

    const config = JSON.stringify({
      functional_description: description,
      reactflow_json_path: 'frontend/src/data/reactflow_data.json'
    });

    // 透過 QWebChannel bridge 呼叫後端
    // QWebChannel 代理方法不支援 ?. 檢查，需直接使用 bridge 物件
    if (bridge) {
      try {
        // QWebChannel @pyqtSlot(str, result=str) 方法：傳入字串，回傳字串
        // 使用回調模式（QWebChannel 非同步呼叫）
        bridge.run_ai_risk_analysis(config, (resultStr) => {
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
  }, [bridge, description]);

  const handlePathClick = useCallback((pathItem) => {
    setSelectedPathId(pathItem.path_id);
    setExpandedPathId(prev => prev === pathItem.path_id ? null : pathItem.path_id);
    if (onSelectPath) {
      onSelectPath(pathItem.node_ids, pathItem);
    }
  }, [onSelectPath]);

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

  return (
    <div style={{
      position: 'absolute',
      top: '20px',
      right: '20px',
      width: '420px',
      maxHeight: 'calc(100vh - 160px)',
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
        <span style={{ color: '#667eea', fontWeight: '700', fontSize: '15px' }}>
           AI 風險預測分析
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

      {/* 功能描述輸入 */}
      <div style={{ padding: '14px 18px', borderBottom: '1px solid #333' }}>
        <label style={{ color: '#aaa', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
          電路功能描述（AI 將根據此描述判斷電路邏輯是否正確）
        </label>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="例如：此電路為 8-bit 自動閾值計算器，輸入像素資料後計算最大值與最小值之平均作為二值化閾值..."
          style={{
            width: '100%',
            height: '80px',
            background: '#1a1c2a',
            color: '#ddd',
            border: '1px solid #444',
            borderRadius: '6px',
            padding: '10px',
            fontSize: '12px',
            fontFamily: 'inherit',
            resize: 'vertical',
            boxSizing: 'border-box'
          }}
        />
        <button
          onClick={handleAnalyze}
          disabled={isAnalyzing}
          style={{
            marginTop: '10px',
            width: '100%',
            padding: '10px',
            background: isAnalyzing
              ? '#555'
              : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
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
          ⚠ {error}
        </div>
      )}

      {/* 分析摘要 */}
      {summary && (
        <div style={{
          padding: '12px 18px',
          borderBottom: '1px solid #333',
          display: 'flex',
          gap: '12px',
          flexWrap: 'wrap'
        }}>
          <div style={{ color: '#aaa', fontSize: '11px', width: '100%', marginBottom: '4px' }}>
            分析摘要 — 共 {summary.total_paths} 條邏輯路徑
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

      {/* 風險路徑列表 */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '8px 0'
      }}>
        {results && results.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', color: '#888', fontSize: '13px' }}>
            未檢測到任何邏輯路徑
          </div>
        )}

        {results && results.map((item, idx) => (
          <div
            key={item.path_id}
            onClick={() => handlePathClick(item)}
            style={{
              padding: '12px 18px',
              cursor: 'pointer',
              background: selectedPathId === item.path_id
                ? 'rgba(102, 126, 234, 0.15)'
                : 'transparent',
              borderBottom: '1px solid #2a2a2a',
              transition: 'background 0.2s'
            }}
            onMouseEnter={e => {
              if (selectedPathId !== item.path_id)
                e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
            }}
            onMouseLeave={e => {
              if (selectedPathId !== item.path_id)
                e.currentTarget.style.background = 'transparent';
            }}
          >
            {/* 路徑標題行 */}
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
                #{idx + 1} — 風險分數: {(item.risk_score * 100).toFixed(1)}%
              </span>
            </div>

            {/* 路徑描述 */}
            <div style={{
              color: '#9aa',
              fontSize: '11px',
              lineHeight: '1.5',
              wordBreak: 'break-all'
            }}>
              {item.path_str}
            </div>

            {/* 展開：風險原因 */}
            {expandedPathId === item.path_id && (
              <div style={{
                marginTop: '10px',
                padding: '10px',
                background: 'rgba(0,0,0,0.3)',
                borderRadius: '6px',
                borderLeft: `3px solid ${riskLevelColor(item.risk_level)}`
              }}>
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

                {/* 詳細分數 */}
                {item.detail_scores && (
                  <div style={{ marginTop: '8px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {Object.entries(item.detail_scores).map(([key, val]) => (
                      <span key={key} style={{
                        background: 'rgba(102,126,234,0.15)',
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

export default RiskAnalysisPanel;
