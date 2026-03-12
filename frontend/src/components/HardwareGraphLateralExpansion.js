import React, { useState, useCallback, useMemo, useEffect } from 'react';
import ReactFlow, { 
  Controls, 
  Background, 
  useNodesState,
  useEdgesState
} from 'reactflow';
import 'reactflow/dist/style.css';
import styled from 'styled-components';

// 引入自定義節點組件
import HardwareNode from './HardwareNode';
// 引入自定義連線元件
import CustomHardwareEdge from './CustomHardwareEdge';
// 引入測資設定 Modal
import StimulusConfigModal from './StimulusConfigModal';
// 引入 Bridge Hook 用於前後端通訊
import { useBridge } from '../hooks/useBridge';

// 引入 Dagre 佈局工具函式
import { 
  getLayoutedElements, 
  detectTopModule,
  buildInstanceToModuleMap 
} from '../utils/layoutUtils';

// 引入後端產出的資料
import graphData from '../data/reactflow_data.json';
import simulationData from '../data/simulation_data.json';

// ==================== 樣式組件定義 ====================

const StimulusButton = styled.button`
  position: absolute;
  top: 20px;
  left: 20px;
  z-index: 1000;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
  transition: all 0.3s;
  font-family: 'Consolas', monospace;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
  }
  
  &:active {
    transform: translateY(0);
  }
  
  &:disabled {
    background: #444;
    cursor: not-allowed;
    box-shadow: none;
  }
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
  border: 4px solid rgba(102, 126, 234, 0.1);
  border-top-color: #667eea;
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
  font-family: 'Consolas', monospace;
`;

const InfoPanel = styled.div`
  position: absolute;
  bottom: 120px;
  right: 20px;
  z-index: 1000;
  background: rgba(37, 37, 37, 0.95);
  padding: 15px 20px;
  border-radius: 8px;
  border: 1px solid #444;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #aaa;
  max-width: 350px;
`;

// Group 節點專用：半透明背景容器
const ModuleGroupNode = ({ data }) => {
  return (
    <div style={{
      width: '100%',
      height: '100%',
      background: 'rgba(50, 50, 70, 0.15)',
      border: '2px solid rgba(102, 126, 234, 0.4)',
      borderRadius: '12px',
      position: 'relative',
      padding: '20px'
    }}>
      {/* Group 標題列 */}
      <div style={{
        position: 'absolute',
        top: '8px',
        left: '12px',
        fontSize: '14px',
        fontWeight: '700',
        color: '#667eea',
        fontFamily: 'Consolas, monospace',
        letterSpacing: '0.5px'
      }}>
        {data.label}
      </div>
      
      {/* 收合按鈕 */}
      {data.onCollapse && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            data.onCollapse();
          }}
          style={{
            position: 'absolute',
            top: '8px',
            right: '8px',
            background: 'rgba(255, 68, 68, 0.8)',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            padding: '4px 10px',
            cursor: 'pointer',
            fontSize: '12px',
            fontFamily: 'Consolas, monospace',
            fontWeight: '600',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => {
            e.target.style.background = 'rgba(255, 68, 68, 1)';
            e.target.style.transform = 'scale(1.05)';
          }}
          onMouseLeave={(e) => {
            e.target.style.background = 'rgba(255, 68, 68, 0.8)';
            e.target.style.transform = 'scale(1)';
          }}
        >
          收合
        </button>
      )}
    </div>
  );
};

// ==================== 主要組件 ====================

const HardwareGraph = () => {
  // 使用 Bridge Hook 進行前後端通訊
  const { bridge } = useBridge();

  // 原始資料狀態（未過濾）
  const [rawNodes] = useState(graphData.reactflow_nodes || []);
  const [rawEdges] = useState(graphData.reactflow_edges || []);
  
  // 時間軸控制：目前在模擬資料中的第幾個步驟
  const [currentTimeIndex, setCurrentTimeIndex] = useState(0);

  // 測資設定 Modal 狀態
  const [isStimulusModalOpen, setIsStimulusModalOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // ==================== 橫向遞迴展開核心狀態 ====================
  
  // 已展開的子模組記錄：{ moduleKey: { x, y, groupId, moduleName, instanceName, parentGroupId } }
  const [expandedModules, setExpandedModules] = useState({});
  
  // 實例名稱到模組定義的映射表
  const [instanceToModuleMap, setInstanceToModuleMap] = useState({});
  
  // 頂層模組名稱
  const [topModule, setTopModule] = useState(null);

  // React Flow 節點與連線狀態（使用 Hook 管理）
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // 註冊自定義節點類型與連線類型
  const nodeTypes = useMemo(() => ({ 
    customNode: HardwareNode,
    groupNode: ModuleGroupNode
  }), []);

  const edgeTypes = useMemo(() => ({ 
    hardwareEdge: CustomHardwareEdge
  }), []);

  // ==================== 初始化：偵測頂層模組並建立根 Group ====================
  
  useEffect(() => {
    if (rawNodes.length === 0) return;

    // 偵測頂層模組
    const detectedTopModule = detectTopModule(rawNodes);
    console.log('[初始化] 偵測到頂層模組:', detectedTopModule);
    
    // 建立實例映射表
    const instanceMap = buildInstanceToModuleMap(rawNodes);
    console.log('[初始化] 實例映射表:', instanceMap);
    
    setTopModule(detectedTopModule);
    setInstanceToModuleMap(instanceMap);

    // 建立根 Group
    const rootGroupId = `group_ROOT_${detectedTopModule}`;
    
    // 過濾出頂層模組的所有節點
    const rootVariableNodes = rawNodes.filter(n => 
      n.data?.module === detectedTopModule && n.data?.type !== 'submodule'
    );
    const rootSubmoduleNodes = rawNodes.filter(n => 
      n.data?.module === detectedTopModule && n.data?.type === 'submodule'
    );
    const rootAllNodes = [...rootVariableNodes, ...rootSubmoduleNodes];

    console.log('[初始化] 頂層節點數量:', rootAllNodes.length);

    // 過濾出頂層模組的所有連線
    const rootNodeIds = new Set(rootAllNodes.map(n => n.id));
    const rootEdgeList = rawEdges.filter(e => 
      rootNodeIds.has(e.source) && rootNodeIds.has(e.target)
    );

    // 使用 Dagre 佈局
    const layouted = getLayoutedElements(rootAllNodes, rootEdgeList);
    const layoutedNodes = layouted.nodes || layouted; // 相容不同回傳格式
    const layoutedEdges = layouted.edges || rootEdgeList;

    console.log('[初始化] Dagre 佈局完成:', layoutedNodes.length, '節點');

    // 計算 Group 邊界（內部節點的範圍）
    const bounds = calculateBounds(layoutedNodes);
    const groupWidth = bounds.maxX - bounds.minX + 200; // 留出邊距
    const groupHeight = bounds.maxY - bounds.minY + 200;

    console.log('[初始化] Group 尺寸:', groupWidth, 'x', groupHeight);

    // 建立根 Group 節點
    const rootGroup = {
      id: rootGroupId,
      type: 'groupNode',
      position: { x: 50, y: 50 },
      style: {
        width: groupWidth,
        height: groupHeight,
        zIndex: -1 // 背景層
      },
      data: {
        label: `${detectedTopModule} (根模組)`,
        onCollapse: null // 根 Group 不可收合
      }
    };

    // 將內部節點設定為 Group 的子節點
    const childNodes = layoutedNodes.map(n => ({
      ...n,
      parentNode: rootGroupId,
      extent: 'parent',
      position: {
        x: n.position.x - bounds.minX + 100,
        y: n.position.y - bounds.minY + 100
      }
    }));

    // 設定連線類型為自定義連線
    const customEdges = layoutedEdges.map(e => ({
      ...e,
      type: 'hardwareEdge'
    }));

    // 記錄根模組展開狀態
    setExpandedModules({
      [`ROOT_${detectedTopModule}`]: {
        x: 50,
        y: 50,
        groupId: rootGroupId,
        moduleName: detectedTopModule,
        instanceName: 'ROOT',
        parentGroupId: null
      }
    });

    // 設定初始節點與連線
    setNodes([rootGroup, ...childNodes]);
    setEdges(customEdges);

    console.log('[初始化] 完成 - 總節點數:', 1 + childNodes.length);

  }, [rawNodes, rawEdges, setNodes, setEdges]);

  // ==================== 工具函式：計算節點邊界 ====================
  
  const calculateBounds = useCallback((nodeList) => {
    if (nodeList.length === 0) {
      return { minX: 0, minY: 0, maxX: 600, maxY: 400 };
    }

    let minX = Infinity, minY = Infinity;
    let maxX = -Infinity, maxY = -Infinity;

    nodeList.forEach(node => {
      const x = node.position.x;
      const y = node.position.y;
      const width = 180; // 預設寬度
      const height = 90; // 預設高度

      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + width);
      maxY = Math.max(maxY, y + height);
    });

    return { minX, minY, maxX, maxY };
  }, []);

  // ==================== 核心函式：展開子模組 ====================
  
  const expandModule = useCallback((instanceName, moduleName, parentGroupId, baseX, baseY) => {
    const moduleKey = `${moduleName}_inst_${instanceName}`;
    
    // 檢查是否已展開
    if (expandedModules[moduleKey]) {
      console.log('[展開] 模組已展開，忽略:', moduleKey);
      return;
    }

    console.log('[展開] 開始展開子模組:', {
      instanceName,
      moduleName,
      parentGroupId,
      baseX,
      baseY
    });

    // 過濾出該模組的內部節點
    const moduleVariableNodes = rawNodes.filter(n => 
      n.data?.module === moduleName && n.data?.type !== 'submodule'
    );
    const moduleSubmoduleNodes = rawNodes.filter(n => 
      n.data?.module === moduleName && n.data?.type === 'submodule'
    );
    const moduleAllNodes = [...moduleVariableNodes, ...moduleSubmoduleNodes];

    if (moduleAllNodes.length === 0) {
      console.warn('[展開] 無法找到模組內部節點:', moduleName);
      alert(`無法展開模組「${moduleName}」：找不到內部實作`);
      return;
    }

    console.log('[展開] 找到內部節點:', moduleAllNodes.length);

    // 過濾出該模組的內部連線
    const moduleNodeIds = new Set(moduleAllNodes.map(n => n.id));
    const moduleEdgeList = rawEdges.filter(e => 
      moduleNodeIds.has(e.source) && moduleNodeIds.has(e.target)
    );

    // 使用 Dagre 佈局
    const layouted = getLayoutedElements(moduleAllNodes, moduleEdgeList);
    const layoutedNodes = layouted.nodes || layouted;
    const layoutedEdges = layouted.edges || moduleEdgeList;

    console.log('[展開] Dagre 佈局完成');

    // 計算 Group 邊界
    const bounds = calculateBounds(layoutedNodes);
    const groupWidth = bounds.maxX - bounds.minX + 200;
    const groupHeight = bounds.maxY - bounds.minY + 200;

    console.log('[展開] 新 Group 尺寸:', groupWidth, 'x', groupHeight);

    // 建立新 Group ID
    const newGroupId = `group_${moduleKey}`;

    // 建立 Group 節點
    const newGroup = {
      id: newGroupId,
      type: 'groupNode',
      position: { x: baseX, y: baseY },
      style: {
        width: groupWidth,
        height: groupHeight,
        zIndex: -1
      },
      data: {
        label: `${moduleName} (${instanceName})`,
        onCollapse: () => collapseModule(moduleKey)
      }
    };

    // 將內部節點設定為 Group 的子節點（關鍵：加入 parentNode 與 extent 屬性）
    const childNodes = layoutedNodes.map(n => ({
      ...n,
      id: `${newGroupId}_${n.id}`, // 防止 ID 衝突
      parentNode: newGroupId,
      extent: 'parent', // 限制在父節點內
      position: {
        x: n.position.x - bounds.minX + 100,
        y: n.position.y - bounds.minY + 100
      }
    }));

    console.log('[展開] 建立子節點:', childNodes.length);

    // 設定連線類型（關鍵：使用自定義連線元件）
    const customEdges = layoutedEdges.map(e => ({
      ...e,
      id: `${newGroupId}_${e.id}`, // 防止 ID 衝突
      source: `${newGroupId}_${e.source}`,
      target: `${newGroupId}_${e.target}`,
      type: 'hardwareEdge'
    }));

    console.log('[展開] 建立連線:', customEdges.length);

    // 更新展開記錄
    setExpandedModules(prev => ({
      ...prev,
      [moduleKey]: {
        x: baseX,
        y: baseY,
        groupId: newGroupId,
        moduleName,
        instanceName,
        parentGroupId
      }
    }));

    // 動態新增節點與連線（關鍵：透過 setNodes 與 setEdges 更新）
    setNodes(prevNodes => {
      console.log('[展開] 動態新增節點 - 原有:', prevNodes.length, '→ 新增:', 1 + childNodes.length);
      return [...prevNodes, newGroup, ...childNodes];
    });
    
    setEdges(prevEdges => {
      console.log('[展開] 動態新增連線 - 原有:', prevEdges.length, '→ 新增:', customEdges.length);
      return [...prevEdges, ...customEdges];
    });

    console.log('[展開] ✓ 完成 - GroupID:', newGroupId);

  }, [rawNodes, rawEdges, expandedModules, calculateBounds, setNodes, setEdges]);

  // ==================== 核心函式：收合子模組 ====================
  
  const collapseModule = useCallback((moduleKey) => {
    console.log('[收合] 開始收合模組:', moduleKey);

    const moduleInfo = expandedModules[moduleKey];
    if (!moduleInfo) {
      console.warn('[收合] 找不到展開記錄:', moduleKey);
      return;
    }

    // 遞迴收合所有子模組
    const removeRecursive = (key) => {
      const module = expandedModules[key];
      if (!module) return;

      console.log('[收合] 處理模組:', key, '(GroupID:', module.groupId, ')');

      // 找出所有子模組
      Object.keys(expandedModules).forEach(childKey => {
        if (expandedModules[childKey].parentGroupId === module.groupId) {
          console.log('[收合] 發現子模組:', childKey);
          removeRecursive(childKey);
        }
      });

      // 移除該模組的所有節點與連線
      setNodes(prevNodes => {
        const filtered = prevNodes.filter(n => 
          n.id !== module.groupId && n.parentNode !== module.groupId
        );
        console.log('[收合] 移除節點 -', prevNodes.length, '→', filtered.length);
        return filtered;
      });
      
      setEdges(prevEdges => {
        const filtered = prevEdges.filter(e => 
          !e.id.startsWith(`${module.groupId}_`)
        );
        console.log('[收合] 移除連線 -', prevEdges.length, '→', filtered.length);
        return filtered;
      });

      // 從展開記錄中刪除
      setExpandedModules(prev => {
        const updated = { ...prev };
        delete updated[key];
        return updated;
      });

      console.log('[收合] ✓ 已移除模組:', key);
    };

    removeRecursive(moduleKey);

  }, [expandedModules, setNodes, setEdges]);

  // ==================== 事件處理：雙擊節點展開子模組 ====================
  
  const handleNodeDoubleClick = useCallback((event, node) => {
    console.log('[雙擊] 觸發 - 節點:', node.id, '類型:', node.data?.type);

    // 只處理 submodule 類型節點
    if (node.data?.type !== 'submodule') {
      console.log('[雙擊] 非子模組節點，忽略');
      return;
    }

    const instanceName = node.data.label;
    const targetModule = instanceToModuleMap[instanceName];

    console.log('[雙擊] 實例:', instanceName, '→ 模組:', targetModule);

    if (!targetModule) {
      console.warn('[雙擊] 找不到實例映射:', instanceName);
      alert(`無法展開：找不到實例「${instanceName}」的模組定義`);
      return;
    }

    // 計算新 Group 的位置（向右偏移 800px）
    const parentGroupId = node.parentNode;
    
    // 從 expandedModules 中找出父 Group 的資訊
    let parentGroup = null;
    for (const key in expandedModules) {
      if (expandedModules[key].groupId === parentGroupId) {
        parentGroup = expandedModules[key];
        break;
      }
    }

    const baseX = parentGroup ? parentGroup.x + 800 : 850; // 橫向偏移
    const baseY = parentGroup ? parentGroup.y : 50;

    console.log('[雙擊] 計算新 Group 位置:', {
      parentGroupId,
      baseX,
      baseY
    });

    // 展開子模組
    expandModule(instanceName, targetModule, parentGroupId, baseX, baseY);

  }, [instanceToModuleMap, expandedModules, expandModule]);

  // ==================== 測資設定相關函式 ====================
  
  const handleOpenStimulusModal = useCallback(() => {
    setIsStimulusModalOpen(true);
  }, []);

  const handleCloseStimulusModal = useCallback(() => {
    setIsStimulusModalOpen(false);
  }, []);

  const handleGenerateStimulus = useCallback(async (stimulusConfig) => {
    setIsGenerating(true);
    try {
      console.log('[測資生成] 設定:', stimulusConfig);
      
      if (bridge?.generate_auto_tb) {
        const configJson = JSON.stringify(stimulusConfig, null, 2);
        
        bridge.generate_auto_tb(configJson, (result) => {
          console.log('[測資生成] 後端回應:', result);
          try {
            const response = JSON.parse(result);
            if (response.success) {
              console.log('[測資生成] 成功:', response.message);
              alert(`測資生成成功！\n${response.message}\n\n請重新載入頁面查看最新模擬結果。`);
              setTimeout(() => window.location.reload(), 2000);
            } else {
              console.error('[測資生成] 失敗:', response.error);
              alert(`測資生成失敗：\n${response.error}`);
            }
          } catch (err) {
            console.error('[測資生成] 解析回應失敗:', err);
            alert('後端回應格式錯誤，請檢查 Console 輸出');
          } finally {
            setIsGenerating(false);
          }
        });
      } else {
        console.warn('[測資生成] Bridge 未就緒');
        setIsGenerating(false);
        alert('後端通訊未就緒，請確認 Bridge 連接狀態');
      }
      
      setIsStimulusModalOpen(false);
    } catch (error) {
      console.error('[測資生成] 錯誤:', error);
      alert(`執行錯誤：\n${error.message}`);
      setIsGenerating(false);
    }
  }, [bridge]);

  // ==================== 時間軸控制 ====================
  
  useEffect(() => {
    // simulation_data.json 實際結構：
    // { time_steps: [5000, 10000, ...], signals: { "clk": ["0","1",...], "reset": [...], ... } }
    if (!simulationData || !simulationData.signals || !simulationData.time_steps) return;
    if (currentTimeIndex >= simulationData.time_steps.length) return;

    const signals = simulationData.signals;

    // 更新節點的即時邏輯值
    setNodes(prevNodes => prevNodes.map(node => {
      if (node.type === 'groupNode') return node;
      
      const signalName = node.data?.label;
      const signalArray = signals[signalName];

      if (signalArray && currentTimeIndex < signalArray.length) {
        const signalValue = signalArray[currentTimeIndex];
        return {
          ...node,
          data: {
            ...node.data,
            currentValue: signalValue
          }
        };
      }
      return node;
    }));

    // 更新連線的即時邏輯值
    setEdges(prevEdges => prevEdges.map(edge => {
      const sourceSignalName = edge.source;
      const signalArray = signals[sourceSignalName];

      if (signalArray && currentTimeIndex < signalArray.length) {
        const signalValue = signalArray[currentTimeIndex];

        let signalType = 'data';
        const srcLower = sourceSignalName.toLowerCase();
        if (srcLower === 'clk' || srcLower === 'clock') {
          signalType = 'clock';
        } else if (srcLower.includes('rst') || srcLower.includes('reset')) {
          signalType = 'reset';
        }

        return {
          ...edge,
          type: 'custom',
          data: {
            ...edge.data,
            currentValue: signalValue,
            signalType: signalType
          }
        };
      }
      return edge;
    }));

  }, [currentTimeIndex, simulationData, setNodes, setEdges]);

  // 滑桿變更事件
  const handleTimeChange = useCallback((e) => {
    setCurrentTimeIndex(parseInt(e.target.value, 10));
  }, []);

  // 計算時間標記
  const currentTimeNs = simulationData.time_steps ? simulationData.time_steps[currentTimeIndex] : 0;
  const maxSteps = simulationData.time_steps ? simulationData.time_steps.length - 1 : 0;

  // ==================== 統計資訊 ====================
  
  const stats = useMemo(() => {
    const expandedCount = Object.keys(expandedModules).length;
    const totalNodes = nodes.length;
    const groupCount = nodes.filter(n => n.type === 'groupNode').length;
    const variableCount = nodes.filter(n => n.type === 'customNode').length;
    
    return {
      expandedCount,
      totalNodes,
      groupCount,
      variableCount
    };
  }, [expandedModules, nodes]);

  // ==================== 渲染 UI ====================
  
  return (
    <div style={{ width: '100%', height: '100vh', background: '#0d1117', display: 'flex', flexDirection: 'column' }}>
      {/* Loading Overlay */}
      {isGenerating && (
        <LoadingOverlay>
          <LoadingSpinner />
          <LoadingText>正在生成測資中...</LoadingText>
        </LoadingOverlay>
      )}

      {/* 測資設定按鈕 */}
      <StimulusButton onClick={handleOpenStimulusModal} disabled={!bridge || isGenerating}>
        {isGenerating ? '生成中...' : '測資與時脈設定 (Auto-TB)'}
      </StimulusButton>

      {/* 資訊面板 */}
      <InfoPanel>
        <div style={{ marginBottom: '8px', color: '#667eea', fontWeight: '700' }}>
          系統資訊
        </div>
        <div>已展開模組: {stats.expandedCount}</div>
        <div>總節點數: {stats.totalNodes}</div>
        <div>Group 容器: {stats.groupCount}</div>
        <div>變數節點: {stats.variableCount}</div>
        <div style={{ marginTop: '10px', fontSize: '10px', color: '#888', borderTop: '1px solid #333', paddingTop: '8px' }}>
          操作提示：<br/>
          - 雙擊灰色子模組方塊可展開內部結構<br/>
          - 點擊 Group 右上角「收合」按鈕可關閉<br/>
          - 橫向遞迴展開不會清空現有畫面
        </div>
      </InfoPanel>

      {/* React Flow 畫布 */}
      <div style={{ flex: 1 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDoubleClick={handleNodeDoubleClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          attributionPosition="bottom-left"
          style={{ background: '#0d1117' }}
        >
          <Background color="#21262d" gap={16} />
          <Controls style={{ button: { background: '#21262d', color: '#fff', borderColor: '#30363d' } }} />
        </ReactFlow>
      </div>

      {/* 測資設定 Modal */}
      {isStimulusModalOpen && (
        <StimulusConfigModal
          isOpen={isStimulusModalOpen}
          onClose={handleCloseStimulusModal}
          hierarchyData={graphData}
          onGenerate={handleGenerateStimulus}
        />
      )}

      {/* 底部時間控制列 */}
      <div style={{
        height: '100px',
        background: '#252525',
        padding: '20px 50px',
        borderTop: '1px solid #444',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center'
      }}>
        <div style={{ color: '#fff', marginBottom: '10px', fontFamily: 'monospace', textAlign: 'center' }}>
          <strong>模擬時間: {currentTimeNs} ns</strong> 
          <span style={{ marginLeft: '20px', color: '#888' }}>步進: {currentTimeIndex}/{maxSteps}</span>
          <span style={{ marginLeft: '20px', color: '#667eea' }}>頂層模組: {topModule || '...'}</span>
        </div>
        <input 
          type="range" 
          min="0" 
          max={maxSteps} 
          value={currentTimeIndex} 
          onChange={handleTimeChange}
          style={{ width: '100%', cursor: 'pointer' }}
        />
      </div>
    </div>
  );
};

export default HardwareGraph;
