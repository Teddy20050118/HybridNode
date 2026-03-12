// ==================== Dagre 自動佈局工具函式 ====================
// 此模組負責使用 Dagre 演算法計算節點的最佳位置
// 用於階層式硬體電路視覺化，確保節點間距合理、連線不重疊

import dagre from 'dagre';

/**
 * 使用 Dagre 演算法計算節點佈局
 * 
 * @param {Array} nodes - React Flow 節點陣列
 * @param {Array} edges - React Flow 連線陣列
 * @param {Object} options - 佈局選項
 * @returns {Array} 包含新位置的節點陣列
 */
export const getLayoutedElements = (nodes, edges, options = {}) => {
  // 建立 Dagre 有向圖實例
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  // 設定佈局參數
  const layoutOptions = {
    rankdir: options.direction || 'LR', // 方向：LR (左到右), TB (上到下)
    ranksep: options.ranksep || 120,    // 階層間距 (縱向)
    nodesep: options.nodesep || 80,     // 同層節點間距 (橫向)
    edgesep: options.edgesep || 40,     // 連線間距
    align: options.align || 'UL',       // 對齊方式
    ...options
  };

  dagreGraph.setGraph(layoutOptions);

  // 將節點加入 Dagre 圖形
  nodes.forEach((node) => {
    // 根據節點類型設定不同的尺寸
    const nodeWidth = getNodeWidth(node);
    const nodeHeight = getNodeHeight(node);

    dagreGraph.setNode(node.id, {
      width: nodeWidth,
      height: nodeHeight
    });
  });

  // 將連線加入 Dagre 圖形
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // 執行佈局計算
  dagre.layout(dagreGraph);

  // 將計算結果套用回節點
  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    
    // Dagre 回傳的是節點中心點座標，需要轉換為左上角座標
    const nodeWidth = getNodeWidth(node);
    const nodeHeight = getNodeHeight(node);

    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2
      }
    };
  });

  return layoutedNodes;
};

/**
 * 根據節點類型決定寬度
 * 子模組實例：較大 (180px)
 * 變數節點：較小 (120px)
 */
const getNodeWidth = (node) => {
  const nodeType = node.data?.type;
  
  if (nodeType === 'submodule') {
    return 180; // 子模組實例寬度
  }
  
  // 變數節點 (input, output, wire, reg)
  return 120;
};

/**
 * 根據節點類型決定高度
 * 子模組實例：較高 (90px)
 * 變數節點：較矮 (50px)
 */
const getNodeHeight = (node) => {
  const nodeType = node.data?.type;
  
  if (nodeType === 'submodule') {
    return 90; // 子模組實例高度
  }
  
  // 變數節點 (input, output, wire, reg)
  return 50;
};

/**
 * 偵測所有模組並統計節點數量
 * 用於自動識別頂層模組
 * 
 * @param {Array} nodes - 所有節點
 * @returns {Object} 模組統計資訊 { moduleName: count, ... }
 */
export const getModuleStatistics = (nodes) => {
  const moduleCounts = {};
  
  nodes.forEach(node => {
    const module = node.data?.module;
    if (module) {
      moduleCounts[module] = (moduleCounts[module] || 0) + 1;
    }
  });
  
  return moduleCounts;
};

/**
 * 識別頂層模組
 * 策略：節點數量最多的模組為頂層模組
 * 
 * @param {Array} nodes - 所有節點
 * @returns {string} 頂層模組名稱
 */
export const detectTopModule = (nodes) => {
  const moduleCounts = getModuleStatistics(nodes);
  
  if (Object.keys(moduleCounts).length === 0) {
    return null;
  }
  
  // 找出節點數量最多的模組
  const topModule = Object.keys(moduleCounts).reduce((a, b) => 
    moduleCounts[a] > moduleCounts[b] ? a : b
  );
  
  return topModule;
};

/**
 * 建立實例名稱到模組定義的映射表
 * 透過分析節點標籤推斷子模組類型
 * 
 * @param {Array} nodes - 所有節點
 * @returns {Object} 映射表 { instanceName: moduleDefinition, ... }
 */
export const buildInstanceToModuleMap = (nodes) => {
  const instanceMap = {};
  
  // 策略 1: 透過實例名稱前綴推斷模組類型
  // 例如：f0, f1, f2 -> FIFO_64
  //      mm0, mm1 -> MAX_MIN
  //      F1, F2 -> FIFO_64
  const prefixPatterns = {
    'f': 'FIFO_64',    // 小寫 f 開頭
    'F': 'FIFO_64',    // 大寫 F 開頭
    'mm': 'MAX_MIN',   // mm 開頭
    'ha': 'HA',        // ha 開頭
    'fa': 'FA'         // fa 開頭
  };
  
  nodes.forEach(node => {
    if (node.data?.type === 'submodule') {
      const instanceName = node.data.label || node.id;
      
      // 嘗試匹配前綴模式
      for (const [prefix, moduleType] of Object.entries(prefixPatterns)) {
        if (instanceName.toLowerCase().startsWith(prefix.toLowerCase())) {
          instanceMap[instanceName] = moduleType;
          break;
        }
      }
      
      // 如果沒有匹配到，使用實例名稱的大寫版本作為預設
      if (!instanceMap[instanceName]) {
        instanceMap[instanceName] = instanceName.toUpperCase();
      }
    }
  });
  
  return instanceMap;
};
