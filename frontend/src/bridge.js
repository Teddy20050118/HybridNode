/**
 * HybridNode Frontend Integration Guide
 * 前端 JavaScript 與 PyQt6 QWebChannel 整合範例
 * 
 * 此文件展示如何在 React 前端中調用 Python 後端的橋接函數
 */

// ============================================================
// 1. 引入 QWebChannel 庫
// ============================================================

/**
 * 方法一：從 CDN 引入（在 public/index.html 中）
 * 
 * <script src="https://cdn.jsdelivr.net/npm/@qtproject/qtwebchannel@5.15.2/qwebchannel.js"></script>
 * 
 * 或從本地複製 qwebchannel.js 到 public/ 目錄：
 * 
 * <script src="%PUBLIC_URL%/qwebchannel.js"></script>
 */


// ============================================================
// 2. 初始化 QWebChannel 連接
// ============================================================

/**
 * 在 React App.js 或專用 hook 中初始化
 * 
 * 注意：必須等待 qt.webChannelTransport 可用
 */

class HybridNodeBridge {
  constructor() {
    this.bridge = null;
    this.isReady = false;
    this.readyCallbacks = [];
  }

  /**
   * 初始化 QWebChannel 連接
   * 
   * @returns {Promise} 連接建立後 resolve
   */
  initialize() {
    return new Promise((resolve, reject) => {
      if (typeof QWebChannel === 'undefined') {
        reject(new Error('QWebChannel not loaded. Make sure qwebchannel.js is included in index.html'));
        return;
      }

      // 等待 qt.webChannelTransport 可用
      if (typeof qt !== 'undefined' && qt.webChannelTransport) {
        this._setupChannel(resolve);
      } else {
        // 在某些情況下需要延遲初始化
        document.addEventListener('DOMContentLoaded', () => {
          if (typeof qt !== 'undefined' && qt.webChannelTransport) {
            this._setupChannel(resolve);
          } else {
            reject(new Error('qt.webChannelTransport not available'));
          }
        });
      }
    });
  }

  /**
   * 設置 WebChannel
   * @private
   */
  _setupChannel(resolve) {
    new QWebChannel(qt.webChannelTransport, (channel) => {
      this.bridge = channel.objects.bridge;
      this.isReady = true;

      // 連接 Python 信號到 JavaScript 回調
      this._connectSignals();

      console.log('[SUCCESS] HybridNode Bridge connected!');
      
      resolve(this.bridge);
      
      // 執行等待中的回調
      this.readyCallbacks.forEach(callback => callback(this.bridge));
      this.readyCallbacks = [];
    });
  }

  /**
   * 連接 Python 信號到 JavaScript 事件
   * @private
   */
  _connectSignals() {
    // 分析進度更新
    this.bridge.analysisProgress.connect((message, percentage) => {
      console.log(`[PROGRESS] Analysis Progress: ${percentage}% - ${message}`);
      
      // 觸發自定義事件
      window.dispatchEvent(new CustomEvent('hybridnode:progress', {
        detail: { message, percentage }
      }));
    });

    // 分析完成
    this.bridge.analysisComplete.connect((jsonData) => {
      console.log('[COMPLETE] Analysis Complete!');
      
      const graphData = JSON.parse(jsonData);
      
      window.dispatchEvent(new CustomEvent('hybridnode:complete', {
        detail: graphData
      }));
    });

    // 分析錯誤
    this.bridge.analysisError.connect((errorMessage) => {
      console.error('[ERROR] Analysis Error:', errorMessage);
      
      window.dispatchEvent(new CustomEvent('hybridnode:error', {
        detail: { error: errorMessage }
      }));
    });

    // 資料夾選擇
    this.bridge.directorySelected.connect((path) => {
      console.log('[SELECT] Directory Selected:', path);
      
      window.dispatchEvent(new CustomEvent('hybridnode:directorySelected', {
        detail: { path }
      }));
    });

    // 圖數據載入
    this.bridge.graphDataLoaded.connect((jsonData) => {
      console.log('[LOADED] Graph Data Loaded');
      
      const graphData = JSON.parse(jsonData);
      
      window.dispatchEvent(new CustomEvent('hybridnode:graphLoaded', {
        detail: graphData
      }));
    });
  }

  /**
   * 等待 Bridge 準備就緒
   * 
   * @param {Function} callback 
   */
  onReady(callback) {
    if (this.isReady) {
      callback(this.bridge);
    } else {
      this.readyCallbacks.push(callback);
    }
  }

  /**
   * 開啟資料夾選擇對話框
   */
  openDirectoryDialog() {
    if (!this.isReady) {
      console.error('Bridge not ready');
      return;
    }

    console.log('[DIALOG] Opening directory dialog...');
    this.bridge.open_directory_dialog();
  }

  /**
   * 開始分析專案
   * 
   * @param {string} projectPath 專案路徑
   */
  analyzeProject(projectPath) {
    if (!this.isReady) {
      console.error('Bridge not ready');
      return;
    }

    console.log('🚀 Starting analysis for:', projectPath);
    this.bridge.analyze_project(projectPath);
  }

  /**
   * 載入已存在的圖數據
   * 
   * @param {string} graphPath 圖數據文件路徑（默認 "output/graph_data.pt"）
   * @returns {Promise<Object>} 圖數據
   */
  async loadExistingGraph(graphPath = 'output/graph_data.pt') {
    if (!this.isReady) {
      throw new Error('Bridge not ready');
    }

    console.log('📂 Loading existing graph:', graphPath);
    
    return new Promise((resolve, reject) => {
      // 註冊一次性監聽器
      const handler = (event) => {
        window.removeEventListener('hybridnode:graphLoaded', handler);
        window.removeEventListener('hybridnode:error', errorHandler);
        resolve(event.detail);
      };

      const errorHandler = (event) => {
        window.removeEventListener('hybridnode:graphLoaded', handler);
        window.removeEventListener('hybridnode:error', errorHandler);
        reject(new Error(event.detail.error));
      };

      window.addEventListener('hybridnode:graphLoaded', handler);
      window.addEventListener('hybridnode:error', errorHandler);

      // 調用 Python 函數
      this.bridge.load_existing_graph(graphPath);
    });
  }

  /**
   * 獲取圖統計信息
   * 
   * @returns {Promise<Object>} 統計數據
   */
  async getGraphStats() {
    if (!this.isReady) {
      throw new Error('Bridge not ready');
    }

    const statsJson = this.bridge.get_graph_stats();
    return JSON.parse(statsJson);
  }
}


// ============================================================
// 3. React Hook 封裝（推薦用法）
// ============================================================

/**
 * useHybridNodeBridge Hook
 * 
 * 使用範例：
 * 
 * ```jsx
 * import { useHybridNodeBridge } from './hooks/useHybridNodeBridge';
 * 
 * function App() {
 *   const { bridge, isReady, analyzeProject, openDialog } = useHybridNodeBridge();
 *   
 *   return (
 *     <button onClick={openDialog} disabled={!isReady}>
 *       Select Project
 *     </button>
 *   );
 * }
 * ```
 */

// 將此代碼保存到 src/hooks/useHybridNodeBridge.js

/*
import { useState, useEffect } from 'react';

let bridgeInstance = null;

export function useHybridNodeBridge() {
  const [isReady, setIsReady] = useState(false);
  const [graphData, setGraphData] = useState(null);
  const [progress, setProgress] = useState({ message: '', percentage: 0 });
  const [error, setError] = useState(null);

  useEffect(() => {
    // 初始化 Bridge（單例模式）
    if (!bridgeInstance) {
      bridgeInstance = new HybridNodeBridge();
      
      bridgeInstance.initialize()
        .then(() => {
          setIsReady(true);
        })
        .catch((err) => {
          console.error('Failed to initialize bridge:', err);
          setError(err.message);
        });
    } else if (bridgeInstance.isReady) {
      setIsReady(true);
    }

    // 監聽事件
    const handleProgress = (event) => {
      setProgress(event.detail);
    };

    const handleComplete = (event) => {
      setGraphData(event.detail);
      setProgress({ message: 'Complete', percentage: 100 });
    };

    const handleError = (event) => {
      setError(event.detail.error);
    };

    const handleDirectorySelected = (event) => {
      console.log('Directory selected:', event.detail.path);
      // 自動開始分析
      bridgeInstance.analyzeProject(event.detail.path);
    };

    window.addEventListener('hybridnode:progress', handleProgress);
    window.addEventListener('hybridnode:complete', handleComplete);
    window.addEventListener('hybridnode:error', handleError);
    window.addEventListener('hybridnode:directorySelected', handleDirectorySelected);

    return () => {
      window.removeEventListener('hybridnode:progress', handleProgress);
      window.removeEventListener('hybridnode:complete', handleComplete);
      window.removeEventListener('hybridnode:error', handleError);
      window.removeEventListener('hybridnode:directorySelected', handleDirectorySelected);
    };
  }, []);

  return {
    bridge: bridgeInstance,
    isReady,
    graphData,
    progress,
    error,
    analyzeProject: (path) => bridgeInstance?.analyzeProject(path),
    openDialog: () => bridgeInstance?.openDirectoryDialog(),
    loadGraph: (path) => bridgeInstance?.loadExistingGraph(path),
    getStats: () => bridgeInstance?.getGraphStats(),
  };
}
*/


// ============================================================
// 4. React 組件使用範例
// ============================================================

/**
 * 完整的 React 組件範例
 * 
 * 保存到 src/components/AnalysisPanel.jsx
 */

/*
import React from 'react';
import { useHybridNodeBridge } from '../hooks/useHybridNodeBridge';

function AnalysisPanel() {
  const { isReady, graphData, progress, error, openDialog, loadGraph } = useHybridNodeBridge();

  const handleSelectProject = () => {
    openDialog();
  };

  const handleLoadExisting = async () => {
    try {
      const data = await loadGraph('output/graph_data.pt');
      console.log('Loaded graph:', data);
    } catch (err) {
      console.error('Failed to load graph:', err);
    }
  };

  return (
    <div className="analysis-panel">
      <h2>HybridNode Desktop</h2>
      
      {!isReady && <p>⏳ Connecting to Python backend...</p>}
      
      {isReady && (
        <>
          <button onClick={handleSelectProject}>
            📁 Select C++ Project
          </button>
          
          <button onClick={handleLoadExisting}>
            📂 Load Existing Analysis
          </button>
          
          {progress.percentage > 0 && (
            <div className="progress">
              <div 
                className="progress-bar" 
                style={{ width: `${progress.percentage}%` }}
              />
              <p>{progress.message} - {progress.percentage}%</p>
            </div>
          )}
          
          {error && (
            <div className="error">
              ❌ Error: {error}
            </div>
          )}
          
          {graphData && (
            <div className="graph-stats">
              <p>✅ Analysis Complete!</p>
              <p>Nodes: {graphData.stats.total_nodes}</p>
              <p>Edges: {graphData.stats.total_links}</p>
              <p>Risky Nodes: {graphData.stats.risky_nodes}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default AnalysisPanel;
*/


// ============================================================
// 5. 全局導出（供舊代碼遷移使用）
// ============================================================

// 如果你的現有代碼使用 fetch('/api/graph')，可以這樣遷移：

/*
// 舊代碼：
const response = await fetch('/api/graph');
const data = await response.json();

// 新代碼：
const bridge = new HybridNodeBridge();
await bridge.initialize();
const data = await bridge.loadExistingGraph();
*/

export default HybridNodeBridge;
