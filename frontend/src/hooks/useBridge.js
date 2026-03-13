/* global QWebChannel, qt */
/**
 * HybridNode Bridge Hook
 * 使用 QWebChannel 与 Python 后端通信
 * 完全替换 axios/fetch 网络请求
 */

import { useState, useEffect, useCallback, useRef } from 'react';

// ===== 全域單例：確保多個 useBridge() 呼叫共用同一個 QWebChannel 連線 =====
let _globalBridge = null;          // 已連線的 bridge 物件
let _globalBridgePromise = null;   // 正在初始化的 Promise（防止重複建立連線）

/**
 * 異步等待 QWebChannel 加載
 * 簡化版本：僅檢查 QWebChannel 是否存在，帶有「最後防線」邏輯
 * @returns {Promise<boolean>} QWebChannel 是否可用
 */
async function waitForWebChannel() {
  const maxAttempts = 20;  // 最多 2 秒
  const interval = 100;     // 每 100ms 檢查一次

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    // 標準檢查：window.QWebChannel
    if (typeof QWebChannel !== 'undefined') {
      console.log(`[QWebChannel] Available (attempt ${attempt}/${maxAttempts})`);
      return true;
    }

    // 「最後防線」：嘗試從 window 對象中尋找（注入位置可能變動）
    if (typeof window !== 'undefined') {
      // 檢查所有可能的位置
      const possibleLocations = [
        window.QWebChannel,
        window['QWebChannel'],
        typeof QWebChannel !== 'undefined' ? QWebChannel : null
      ];

      for (const location of possibleLocations) {
        if (typeof location === 'function') {
          console.log(`[QWebChannel] Found in alternate location (attempt ${attempt}/${maxAttempts})`);
          // 將其提升到全域
          window.QWebChannel = location;
          return true;
        }
      }
    }

    if (attempt % 5 === 0) {
      console.log(`[QWebChannel] Still waiting... (${attempt}/${maxAttempts})`);
    }

    await new Promise(resolve => setTimeout(resolve, interval));
  }

  console.error('[QWebChannel] Not available after 2 seconds');
  console.error('[Diagnostic] Check if qwebchannel.js is properly injected');
  return false;
}

/**
 * 異步等待 qt.webChannelTransport 可用
 * @returns {Promise<boolean>} qt.webChannelTransport 是否可用
 */
async function waitForQtTransport() {
  const maxAttempts = 20;
  const interval = 100;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    if (typeof qt !== 'undefined' && qt.webChannelTransport) {
      console.log(`[Qt] Transport available (attempt ${attempt}/${maxAttempts})`);
      return true;
    }

    if (attempt % 5 === 0) {
      console.log(`[Qt] Waiting for transport... (${attempt}/${maxAttempts})`);
    }

    await new Promise(resolve => setTimeout(resolve, interval));
  }

  console.error('[Qt] Transport not available after 2 seconds');
  console.error('[Warning] This app must run inside PyQt6 WebEngine, not a regular browser');
  return false;
}

/**
 * 初始化 QWebChannel 连接
 * @returns {Promise<Object>} bridge 对象
 */
async function initializeBridge() {
  console.log('[Bridge] Starting initialization...');

  // 检查是否在浏览器环境中
  if (typeof window === 'undefined') {
    throw new Error('Not running in browser environment');
  }

  // 步驟 1: 等待 QWebChannel 類別定義
  console.log('[Bridge] Step 1: Waiting for QWebChannel...');
  const qwebchannelReady = await waitForWebChannel();

  if (!qwebchannelReady) {
    throw new Error(
      'QWebChannel failed to load. Ensure qwebchannel.js is injected or loaded via <script> tag.'
    );
  }

  // 步驟 2: 等待 qt.webChannelTransport（PyQt6 提供）
  console.log('[Bridge] Step 2: Waiting for qt.webChannelTransport...');
  const qtTransportReady = await waitForQtTransport();

  if (!qtTransportReady) {
    throw new Error(
      'qt.webChannelTransport not available. This app must run inside PyQt6 WebEngine.'
    );
  }

  // 步驟 3: 建立 QWebChannel 連接
  console.log('[Bridge] Step 3: Creating QWebChannel connection...');
  return new Promise((resolve, reject) => {
    try {
      new QWebChannel(qt.webChannelTransport, (channel) => {
        if (!channel.objects.bridge) {
          reject(new Error('Bridge object not found in QWebChannel'));
          return;
        }

        console.log('[Bridge] Object connected successfully');
        resolve(channel.objects.bridge);
      });
    } catch (error) {
      console.error('[Bridge] Creation failed:', error);
      reject(error);
    }
  });
}

/**
 * HybridNode Bridge Hook
 * 
 * @returns {Object} {
 *   bridge: 原始 bridge 对象,
 *   isReady: 是否已连接,
 *   connectionStatus: 连接状态 ('connecting' | 'connected' | 'failed'),
 *   graphData: 图数据,
 *   stats: 统计信息,
 *   progress: 分析进度 { message, percentage },
 *   error: 错误信息,
 *   loadExistingGraph: 加载现有图数据,
 *   analyzeProject: 分析新项目,
 *   openDirectoryDialog: 打开文件夹选择对话框
 * }
 */
export function useBridge() {
  const [isReady, setIsReady] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [graphData, setGraphData] = useState(null);
  const [stats, setStats] = useState(null);
  const [progress, setProgress] = useState({ message: '', percentage: 0 });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // bridge 用 state 管理（而非僅用 ref），確保設定後觸發重新渲染
  const [bridge, setBridge] = useState(null);
  const bridgeRef = useRef(null);

  /**
   * 连接 Python 信号
   */
  const connectSignals = useCallback((bridgeObj) => {
    // 测试 ping 连接 - 使用回调方式 (QWebChannel 异步调用)
    if (bridgeObj.ping) {
      // 注意: QWebChannel 的方法调用是异步的，需要传入回调函数
      // 不要直接调用 bridgeObj.ping() 并尝试 JSON.parse 结果
      console.log('[Bridge] Ping test skipped (will use signal-based communication)');
    }

    // 分析进度更新
    bridgeObj.analysisProgress.connect((message, percentage) => {
      console.log(`[Progress] ${percentage}% - ${message}`);
      setProgress({ message, percentage });
      setLoading(percentage < 100);
    });

    // 分析完成
    bridgeObj.analysisComplete.connect((jsonData) => {
      console.log('[Analysis] Complete!');
      try {
        const data = JSON.parse(jsonData);
        setGraphData(data);
        setStats(data.stats || null);
        setLoading(false);
        setProgress({ message: 'Complete', percentage: 100 });
      } catch (err) {
        console.error('[Error] Failed to parse graph data:', err);
        setError('Failed to parse analysis results');
        setLoading(false);
      }
    });

    // 分析错误
    bridgeObj.analysisError.connect((errorMessage) => {
      console.error('[Error] Analysis error:', errorMessage);
      setError(errorMessage);
      setLoading(false);
    });

    // 文件夹选择
    bridgeObj.directorySelected.connect((path) => {
      console.log('[Directory] Selected:', path);
      // 自动开始分析
      setLoading(true);
      setError(null);
      bridgeObj.analyze_project(path);
    });

    // 图数据加载完成
    bridgeObj.graphDataLoaded.connect((jsonData) => {
      console.log('[Graph] Data loaded');
      try {
        const data = JSON.parse(jsonData);
        setGraphData(data);
        setStats(data.stats || null);
        setLoading(false);
      } catch (err) {
        console.error('[Error] Failed to parse loaded graph data:', err);
        setError('Failed to parse graph data');
        setLoading(false);
      }
    });
  }, []);

  // 初始化 Bridge 连接（使用全域單例，多個元件共享同一連線）
  useEffect(() => {
    // 若已有全域 bridge，直接使用
    if (_globalBridge) {
      console.log('[Bridge] Reusing existing global bridge connection');
      bridgeRef.current = _globalBridge;
      setBridge(_globalBridge);
      setIsReady(true);
      setConnectionStatus('connected');
      connectSignals(_globalBridge);
      return;
    }

    console.log('[Bridge] Initializing HybridNode Bridge...');
    setConnectionStatus('connecting');

    // 若已有正在初始化的 Promise，等待它完成（避免重複建立連線）
    if (!_globalBridgePromise) {
      _globalBridgePromise = initializeBridge();
    }

    _globalBridgePromise
      .then((bridgeObj) => {
        console.log('[Bridge] Connected successfully');
        _globalBridge = bridgeObj;  // 快取到全域
        bridgeRef.current = bridgeObj;
        setBridge(bridgeObj);
        setIsReady(true);
        setConnectionStatus('connected');

        // 连接 Python 信号到 JavaScript 回调
        connectSignals(bridgeObj);
      })
      .catch((err) => {
        console.error('[Bridge] Failed to initialize:', err);
        console.error('[Bridge] Diagnostic Info:');
        console.error('   - QWebChannel available:', typeof QWebChannel !== 'undefined');
        console.error('   - qt available:', typeof qt !== 'undefined');
        console.error('   - qt.webChannelTransport available:',
          typeof qt !== 'undefined' && qt.webChannelTransport ? 'yes' : 'no');

        _globalBridgePromise = null;  // 重置，允許下次重試
        setError(err.message);
        setIsReady(false);
        setConnectionStatus('failed');
      });

    // 清理函数
    return () => {
      console.log('[Bridge] Disconnecting...');
    };
  }, [connectSignals]);

  /**
   * 加载现有的图数据
   * 注意：实际数据通过 graphDataLoaded 信号返回
   */
  const loadExistingGraph = useCallback((graphPath = 'output/graph_data.pt') => {
    if (!bridgeRef.current) {
      setError('Bridge not ready');
      return;
    }

    setLoading(true);
    setError(null);

    console.log(`[Graph] Loading existing graph: ${graphPath}`);
    // QWebChannel 方法调用是异步的，结果通过 graphDataLoaded 信号返回
    // 不要试图同步获取返回值
    bridgeRef.current.load_existing_graph(graphPath);
  }, []);

  /**
   * 分析新项目
   */
  const analyzeProject = useCallback((projectPath) => {
    if (!bridgeRef.current) {
      setError('Bridge not ready');
      return;
    }

    console.log(`[Analyze] Starting project analysis: ${projectPath}`);
    setLoading(true);
    setError(null);
    setProgress({ message: 'Starting analysis...', percentage: 0 });

    bridgeRef.current.analyze_project(projectPath);
  }, []);

  /**
   * 打开文件夹选择对话框
   */
  const openDirectoryDialog = useCallback(() => {
    if (!bridgeRef.current) {
      setError('Bridge not ready');
      return;
    }

    console.log('[Dialog] Opening directory dialog...');
    bridgeRef.current.open_directory_dialog();
  }, []);

  /**
   * Reload：先透過 get_last_project_path(callback) 查詢 Python 端儲存的路徑，
   * 若存在則重新執行完整分析（Stage 1-5），否則 fallback 至載入快取。
   *
   * [INFO] 為何不直接呼叫 Python void slot reload_project：
   * QWebChannel JS proxy 對無返回值 @pyqtSlot() 的方法有時無法識別，
   * 改用 result=str 的 get_last_project_path，以 callback 取得路徑後自行定導。
   */
  const reloadProject = useCallback(() => {
    if (!bridgeRef.current) {
      setError('Bridge not ready');
      return;
    }
    console.log('[Reload] Querying last project path...');
    setLoading(true);
    setError(null);
    setProgress({ message: '[RELOAD] 查詢專案路徑...', percentage: 0 });

    bridgeRef.current.get_last_project_path((lastPath) => {
      if (lastPath && lastPath.trim() !== '') {
        console.log(`[Reload] Re-analyzing path: ${lastPath}`);
        setProgress({ message: '[RELOAD] 重新執行完整分析...', percentage: 5 });
        bridgeRef.current.analyze_project(lastPath);
      } else {
        console.log('[Reload] No saved path, loading cache...');
        setProgress({ message: '[RELOAD] 載入快取資料...', percentage: 5 });
        bridgeRef.current.load_existing_graph('output/graph_data.pt');
      }
    });
  }, []);

  return {
    bridge,
    isReady,
    connectionStatus,
    graphData,
    stats,
    progress,
    error,
    loading,
    loadExistingGraph,
    reloadProject,
    analyzeProject,
    openDirectoryDialog,
  };
}

export default useBridge;
