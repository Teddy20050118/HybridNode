import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
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
// 引入自定義連線組件（支援動態邏輯值著色）
import CustomHardwareEdge from './CustomHardwareEdge';
// 引入測資設定 Modal
import StimulusConfigModal from './StimulusConfigModal';
// 引入 Bridge Hook 用於前後端通訊
import { useBridge } from '../hooks/useBridge';

// 引入 Dagre 佈局工具函式
import { getLayoutedElements, detectTopModule } from '../utils/layoutUtils';

// 引入後端產出的資料
import graphData from '../data/reactflow_data.json';
import simulationData from '../data/simulation_data.json';

// ==================== 樣式組件 ====================

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
  
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const LoadVerilogButton = styled.button`
  position: absolute;
  top: 20px;
  left: 220px;
  z-index: 1000;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
  box-shadow: 0 4px 15px rgba(245, 87, 108, 0.4);
  transition: all 0.3s;
  font-family: 'Consolas', monospace;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(245, 87, 108, 0.6);
  }
  
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
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
  const { bridge } = useBridge();

  // 原始資料（完整的所有節點與連線）- 支援動態更新
  const [rawNodes, setRawNodes] = useState(graphData.reactflow_nodes || []);
  const [rawEdges, setRawEdges] = useState(graphData.reactflow_edges || []);
  
  // 時間軸控制
  const [currentTimeIndex, setCurrentTimeIndex] = useState(0);

  // 測資設定 Modal 狀態
  const [isStimulusModalOpen, setIsStimulusModalOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  
  // 載入 Verilog 流水線狀態
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);

  // ==================== Group Nodes 核心狀態 ====================
  
  // 記錄所有已展開的 Group：{ groupId: { moduleName, instanceName, x, y, parentGroupId } }
  const [expandedGroups, setExpandedGroups] = useState({});
  
  // 頂層模組名稱
  const [topModule, setTopModule] = useState(null);

  // React Flow 節點與連線狀態（使用 Hook 管理）
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // 註冊自定義節點類型
  const nodeTypes = useMemo(() => ({ 
    customNode: HardwareNode,
    groupNode: ModuleGroupNode
  }), []);

  // 註冊自定義連線類型
  const edgeTypes = useMemo(() => ({
    custom: CustomHardwareEdge
  }), []);

  // ==================== 初始化：建立頂層 Group ====================
  
  const initializeTopLevelGroup = useCallback(() => {
    if (rawNodes.length === 0) {
      console.warn('[Group Nodes Init] 無節點資料，跳過初始化');
      return;
    }

    // 偵測頂層模組
    const detectedTopModule = detectTopModule(rawNodes);
    console.log('[Group Nodes Init] 頂層模組:', detectedTopModule);
    setTopModule(detectedTopModule);

    // 建立根 Group
    const rootGroupId = `group_ROOT_${detectedTopModule}`;
    
    // 關鍵修復：過濾出頂層模組的所有節點（包含 input, output, wire, reg, submodule）
    const topLevelNodes = rawNodes.filter(n => {
      const nodeModule = n.data?.module;
      const nodeType = n.data?.type;
      
      // 確保節點屬於頂層模組
      const belongsToTopModule = nodeModule === detectedTopModule;
      
      // 顯示所有類型的節點（輸入、輸出、wire、reg、submodule）
      const isValidType = ['input', 'output', 'wire', 'reg', 'submodule'].includes(nodeType);
      
      return belongsToTopModule && isValidType;
    });
    
    const topLevelNodeIds = new Set(topLevelNodes.map(n => n.id));
    const topLevelEdges = rawEdges.filter(e => 
      topLevelNodeIds.has(e.source) && topLevelNodeIds.has(e.target)
    );

    console.log(`[Group Nodes Init] 頂層節點: ${topLevelNodes.length}, 連線: ${topLevelEdges.length}`);
    console.log('[Group Nodes Init] 節點類型統計:', topLevelNodes.reduce((acc, n) => {
      const type = n.data?.type || 'unknown';
      acc[type] = (acc[type] || 0) + 1;
      return acc;
    }, {}));

    // 使用 Dagre 佈局計算頂層節點位置
    const layouted = getLayoutedElements(topLevelNodes, topLevelEdges);
    const layoutedNodes = Array.isArray(layouted) ? layouted : (layouted.nodes || topLevelNodes);

    // 計算 Group 邊界
    const bounds = calculateBounds(layoutedNodes);
    const groupWidth = Math.max(bounds.maxX - bounds.minX + 200, 600);
    const groupHeight = Math.max(bounds.maxY - bounds.minY + 200, 400);

    console.log(`[Group Nodes Init] Group 尺寸: ${groupWidth} x ${groupHeight}`);

    // 建立根 Group 節點
    const rootGroup = {
      id: rootGroupId,
      type: 'groupNode',
      position: { x: 50, y: 50 },
      style: {
        width: groupWidth,
        height: groupHeight,
        zIndex: -1  // 背景層
      },
      data: {
        label: `${detectedTopModule} (根模組)`,
        onCollapse: null  // 根 Group 不可收合
      }
    };

    // 關鍵修復：正確設定每個子節點的 parentNode 與 extent
    const childNodes = layoutedNodes.map(n => {
      const relativePos = {
        x: n.position.x - bounds.minX + 100,
        y: n.position.y - bounds.minY + 100
      };
      
      return {
        ...n,
        parentNode: rootGroupId,
        extent: 'parent',
        position: relativePos,
        // 保留原始節點資料（包含 type, module, target_module 等欄位）
        data: {
          ...n.data
        }
      };
    });

    // 記錄根 Group
    setExpandedGroups({
      [rootGroupId]: {
        moduleName: detectedTopModule,
        instanceName: 'ROOT',
        x: 50,
        y: 50,
        parentGroupId: null
      }
    });

    // 設定初始節點與連線
    setNodes([rootGroup, ...childNodes]);
    setEdges(topLevelEdges);

    console.log(`[Group Nodes Init] 完成 - Group: 1, 子節點: ${childNodes.length}`);

  }, [rawNodes, rawEdges, setNodes, setEdges]);
  
  useEffect(() => {
    initializeTopLevelGroup();
  }, [initializeTopLevelGroup]);

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
      const width = 180;
      const height = 90;

      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + width);
      maxY = Math.max(maxY, y + height);
    });

    return { minX, minY, maxX, maxY };
  }, []);

  // collapseGroup 的 ref，用於打破 expandModule ↔ collapseGroup 的循環依賴
  const collapseGroupRef = useRef(null);

  // ==================== 核心函式：展開子模組（橫向遞迴） ====================
  
  const expandModule = useCallback((instanceId, targetModuleName, parentGroupId, baseX, baseY, fullInstancePath) => {
    const newGroupId = `group_${targetModuleName}_inst_${instanceId}`;
    // fullInstancePath 是完整的實例路徑（如 "th0.f0"），用於 scope_map 查詢
    const instancePath = fullInstancePath || instanceId;
    
    // 檢查是否已展開
    if (expandedGroups[newGroupId]) {
      console.log('[Group Expand] 模組已展開，忽略:', newGroupId);
      return;
    }

    console.log('[Group Expand] 開始展開:', {
      instanceId,
      targetModuleName,
      parentGroupId,
      baseX,
      baseY
    });

    // 從 rawNodes 中過濾出目標模組的內部節點（不依賴 instanceMap）
    const moduleInternalNodes = rawNodes.filter(n => 
      n.data?.module === targetModuleName
    );

    if (moduleInternalNodes.length === 0) {
      console.warn('[Group Expand] 無法找到模組內部節點:', targetModuleName);
      alert(`無法展開模組「${targetModuleName}」：找不到內部實作`);
      return;
    }

    console.log(`[Group Expand] 找到內部節點: ${moduleInternalNodes.length}`);

    // 過濾出該模組的內部連線
    const moduleNodeIds = new Set(moduleInternalNodes.map(n => n.id));
    const moduleInternalEdges = rawEdges.filter(e => 
      moduleNodeIds.has(e.source) && moduleNodeIds.has(e.target)
    );

    // 使用 Dagre 佈局計算內部節點位置
    const layouted = getLayoutedElements(moduleInternalNodes, moduleInternalEdges);
    const layoutedNodes = Array.isArray(layouted) ? layouted : (layouted.nodes || moduleInternalNodes);

    // 計算 Group 邊界
    const bounds = calculateBounds(layoutedNodes);
    const groupWidth = Math.max(bounds.maxX - bounds.minX + 200, 600);
    const groupHeight = Math.max(bounds.maxY - bounds.minY + 200, 400);

    console.log(`[Group Expand] 新 Group 尺寸: ${groupWidth} x ${groupHeight}`);

    // 建立新 Group 節點
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
        label: `${targetModuleName} (${instanceId})`,
        onCollapse: () => collapseGroupRef.current?.(newGroupId)
      }
    };

    // 將內部節點設定為 Group 的子節點
    const childNodes = layoutedNodes.map(n => ({
      ...n,
      id: `${newGroupId}_${n.id}`,  // 防止 ID 衝突
      parentNode: newGroupId,
      extent: 'parent',
      data: {
        ...n.data,
        originalId: n.id,                // 保留原始 ID 供訊號查詢
        instancePath: instancePath        // 完整實例路徑（如 "th0", "th0.f0"）用於 scope_map 查詢
      },
      position: {
        x: n.position.x - bounds.minX + 100,
        y: n.position.y - bounds.minY + 100
      }
    }));

    // 設定連線
    const childEdges = moduleInternalEdges.map(e => ({
      ...e,
      id: `${newGroupId}_${e.id}`,
      source: `${newGroupId}_${e.source}`,
      target: `${newGroupId}_${e.target}`,
      data: {
        ...e.data,
        originalSource: e.source,         // 保留原始 source 供訊號查詢
        originalTarget: e.target,         // 保留原始 target
        instancePath: instancePath        // 完整實例路徑用於 scope_map 查詢
      }
    }));

    // 更新展開記錄
    setExpandedGroups(prev => ({
      ...prev,
      [newGroupId]: {
        moduleName: targetModuleName,
        instanceName: instanceId,
        x: baseX,
        y: baseY,
        parentGroupId
      }
    }));

    // 動態新增節點與連線（不清空現有畫面）
    setNodes(prevNodes => {
      console.log(`[Group Expand] 新增節點 - 原有: ${prevNodes.length} → 新增: ${1 + childNodes.length}`);
      return [...prevNodes, newGroup, ...childNodes];
    });
    
    setEdges(prevEdges => {
      console.log(`[Group Expand] 新增連線 - 原有: ${prevEdges.length} → 新增: ${childEdges.length}`);
      return [...prevEdges, ...childEdges];
    });

    console.log('[Group Expand] 完成 - GroupID:', newGroupId);

  }, [rawNodes, rawEdges, expandedGroups, calculateBounds, setNodes, setEdges]);

  // ==================== 核心函式：收合 Group（遞迴移除） ====================
  
  const collapseGroup = useCallback((groupId) => {
    console.log('[Group Collapse] 開始收合:', groupId);

    // 用函式更新取得最新的 expandedGroups（避免閉包過期問題）
    setExpandedGroups(prevExpanded => {
      const groupInfo = prevExpanded[groupId];
      if (!groupInfo) {
        console.warn('[Group Collapse] 找不到展開記錄:', groupId);
        return prevExpanded;
      }

      // 收集要移除的所有 Group ID（含遞迴子 Group）
      const groupIdsToRemove = new Set();
      const collectRecursive = (currentGroupId) => {
        groupIdsToRemove.add(currentGroupId);
        Object.keys(prevExpanded).forEach(childGroupId => {
          if (prevExpanded[childGroupId].parentGroupId === currentGroupId) {
            collectRecursive(childGroupId);
          }
        });
      };
      collectRecursive(groupId);

      console.log('[Group Collapse] 要移除的 Group:', [...groupIdsToRemove]);

      // 移除節點
      setNodes(prevNodes => {
        const filtered = prevNodes.filter(n =>
          !groupIdsToRemove.has(n.id) && !groupIdsToRemove.has(n.parentNode)
        );
        console.log(`[Group Collapse] 移除節點 - ${prevNodes.length} → ${filtered.length}`);
        return filtered;
      });

      // 移除連線
      setEdges(prevEdges => {
        const filtered = prevEdges.filter(e =>
          ![...groupIdsToRemove].some(gid => e.id.startsWith(`${gid}_`))
        );
        console.log(`[Group Collapse] 移除連線 - ${prevEdges.length} → ${filtered.length}`);
        return filtered;
      });

      // 回傳新的 expandedGroups（刪除所有被移除的 Group）
      const updated = { ...prevExpanded };
      groupIdsToRemove.forEach(gid => delete updated[gid]);
      return updated;
    });

  }, [setNodes, setEdges]);

  // 保持 ref 始終指向最新的 collapseGroup
  collapseGroupRef.current = collapseGroup;

  // ==================== 事件處理：雙擊節點展開（免依賴 instanceMap） ====================
  
  const handleNodeDoubleClick = useCallback((event, node) => {
    console.log('[Double Click] 觸發 - 節點:', node.id, '類型:', node.data?.type);

    // 只處理 submodule 類型節點
    if (node.data?.type !== 'submodule') {
      console.log('[Double Click] 非子模組節點，忽略');
      return;
    }

    // 關鍵：直接從節點資料中讀取 target_module（後端已提供）
    const targetModuleName = node.data.target_module;
    
    if (!targetModuleName) {
      console.warn('[Double Click] 節點缺少 target_module 欄位:', node.id);
      alert(`無法展開：節點「${node.id}」缺少目標模組資訊，請檢查後端解析器`);
      return;
    }

    // 取得原始實例名稱（未加前綴的）
    const originalInstanceId = node.data?.originalId || node.id;
    const instanceId = node.id;
    console.log('[Double Click] 目標模組:', targetModuleName, '實例:', instanceId, '原始ID:', originalInstanceId);

    // 建立完整的實例路徑（用於 scope_map 查詢）
    // 若此節點已有 instancePath（表示它在某個展開的 group 內），則串接
    // 例如：父層 instancePath = "th0"，本節點 originalId = "f0" → 完整路徑 = "th0.f0"
    const parentInstancePath = node.data?.instancePath;
    const fullInstancePath = parentInstancePath 
      ? `${parentInstancePath}.${originalInstanceId}` 
      : originalInstanceId;
    
    console.log('[Double Click] 完整實例路徑:', fullInstancePath);

    // 計算新 Group 的位置（向右偏移 800px）
    const parentGroupId = node.parentNode;
    
    // 從 expandedGroups 中找出父 Group 的資訊
    let parentGroup = null;
    for (const gid in expandedGroups) {
      if (gid === parentGroupId) {
        parentGroup = expandedGroups[gid];
        break;
      }
    }

    const baseX = parentGroup ? parentGroup.x + 800 : 850;  // 橫向偏移
    const baseY = parentGroup ? parentGroup.y : 50;

    console.log('[Double Click] 計算新 Group 位置:', { parentGroupId, baseX, baseY });

    // 展開子模組（傳入完整實例路徑）
    expandModule(instanceId, targetModuleName, parentGroupId, baseX, baseY, fullInstancePath);

  }, [expandedGroups, expandModule]);

  // ==================== 測資設定相關 ====================
  
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

  // ==================== 載入 Verilog 專案（一鍵執行流水線） ====================
  
  const handleLoadVerilogProject = useCallback(async () => {
    if (!bridge) {
      alert('Bridge 未就緒，請稍後再試');
      return;
    }
    
    setIsPipelineRunning(true);
    
    try {
      console.log('[Verilog Pipeline] 開啟檔案選擇對話框');
      
      // 步驟 1：開啟檔案選擇對話框
      bridge.open_verilog_file_dialog((dialogResult) => {
        try {
          const dialogResponse = JSON.parse(dialogResult);
          
          if (dialogResponse.cancelled) {
            console.log('[Verilog Pipeline] 使用者取消選擇');
            setIsPipelineRunning(false);
            return;
          }
          
          if (!dialogResponse.success || !dialogResponse.file_path) {
            console.error('[Verilog Pipeline] 檔案選擇失敗:', dialogResponse.error);
            alert(`檔案選擇失敗：${dialogResponse.error || '未知錯誤'}`);
            setIsPipelineRunning(false);
            return;
          }
          
          const verilogPath = dialogResponse.file_path;
          console.log('[Verilog Pipeline] 選擇的檔案:', verilogPath);
          
          // 步驟 2：執行硬體分析流水線
          console.log('[Verilog Pipeline] 開始執行流水線...');
          
          bridge.run_hardware_pipeline(verilogPath, (pipelineResult) => {
            try {
              const pipelineResponse = JSON.parse(pipelineResult);
              
              if (pipelineResponse.success) {
                console.log('[Verilog Pipeline] 流水線執行成功');
                console.log('[Verilog Pipeline] 回應資料:', pipelineResponse);
                
                // 步驟 3：更新前端資料
                if (pipelineResponse.data) {
                  const newNodes = pipelineResponse.data.reactflow_nodes || [];
                  const newEdges = pipelineResponse.data.reactflow_edges || [];
                  
                  console.log(`[Verilog Pipeline] 更新資料 - 節點: ${newNodes.length}, 連線: ${newEdges.length}`);
                  
                  // 更新 rawNodes 和 rawEdges
                  setRawNodes(newNodes);
                  setRawEdges(newEdges);
                  
                  // 重置展開狀態
                  setExpandedGroups({});
                  
                  // 通知成功
                  alert(`Verilog 專案載入成功！\n\n已解析 ${newNodes.length} 個節點\n畫面即將重新初始化`);
                  
                  // 稍微延遲後重新初始化（讓 useEffect 觸發）
                  setTimeout(() => {
                    setIsPipelineRunning(false);
                  }, 500);
                } else {
                  console.warn('[Verilog Pipeline] 回應中缺少資料');
                  alert(`流水線執行成功，但回應資料格式異常\n請檢查 Console 輸出`);
                  setIsPipelineRunning(false);
                }
              } else {
                console.error('[Verilog Pipeline] 流水線執行失敗:', pipelineResponse.error);
                alert(`流水線執行失敗：\n${pipelineResponse.error || '未知錯誤'}`);
                setIsPipelineRunning(false);
              }
            } catch (err) {
              console.error('[Verilog Pipeline] 解析流水線回應失敗:', err);
              alert(`解析流水線回應失敗：\n${err.message}`);
              setIsPipelineRunning(false);
            }
          });
          
        } catch (err) {
          console.error('[Verilog Pipeline] 解析對話框回應失敗:', err);
          alert(`解析對話框回應失敗：\n${err.message}`);
          setIsPipelineRunning(false);
        }
      });
      
    } catch (error) {
      console.error('[Verilog Pipeline] 執行錯誤:', error);
      alert(`執行錯誤：\n${error.message}`);
      setIsPipelineRunning(false);
    }
  }, [bridge, setRawNodes, setRawEdges]);

  // ==================== 時間軸控制 ====================
  
  useEffect(() => {
    // simulation_data.json 結構：
    // {
    //   time_steps: [5000, 10000, ...],
    //   signals: { "clk": [...], "reset": [...] },              // 扁平（短名稱）
    //   hierarchical_signals: { "sample_tb.uut.clk": [...] },   // 完整階層路徑
    //   scope_map: { "F1.pix_data": "sample_tb.uut.F1.pix_data", ... }
    // }
    if (!simulationData || !simulationData.signals || !simulationData.time_steps) return;
    if (currentTimeIndex >= simulationData.time_steps.length) return;

    const flatSignals = simulationData.signals;
    const hierSignals = simulationData.hierarchical_signals || {};
    const scopeMap = simulationData.scope_map || {};

    /**
     * 查找訊號值的工具函式
     * 策略：
     * 1. 若有 instancePath（展開的子模組），用 "instancePath.signalName" 查 scopeMap → hierSignals
     * 2. 否則用短名稱查 flatSignals（頂層節點）
     */
    const lookupSignalValue = (signalName, instancePath) => {
      let signalArray = null;

      if (instancePath) {
        // 子模組內部訊號：用 scope_map 查找完整路徑
        const scopeKey = `${instancePath}.${signalName}`;
        const fullPath = scopeMap[scopeKey];
        if (fullPath && hierSignals[fullPath]) {
          signalArray = hierSignals[fullPath];
        }
      }

      // Fallback: 用短名稱查扁平訊號
      if (!signalArray && flatSignals[signalName]) {
        signalArray = flatSignals[signalName];
      }

      if (signalArray && currentTimeIndex < signalArray.length) {
        return signalArray[currentTimeIndex];
      }
      return null;
    };

    // 更新節點的即時邏輯值
    setNodes(prevNodes => prevNodes.map(node => {
      if (node.type === 'groupNode') return node;
      
      const signalName = node.data?.originalId || node.data?.label;
      const instancePath = node.data?.instancePath;  // 如 "F1", "th0"
      const signalValue = lookupSignalValue(signalName, instancePath);

      if (signalValue !== null) {
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
      const sourceSignalName = edge.data?.originalSource || edge.source;
      const instancePath = edge.data?.instancePath;
      const signalValue = lookupSignalValue(sourceSignalName, instancePath);

      if (signalValue !== null) {
        // 判斷訊號類型以決定連線著色
        let signalType = 'data';
        const srcLower = sourceSignalName.toLowerCase();
        if (srcLower === 'clk' || srcLower === 'clock') {
          signalType = 'clock';
        } else if (srcLower.includes('rst') || srcLower.includes('reset')) {
          signalType = 'reset';
        }

        return {
          ...edge,
          type: 'custom',  // 使用自定義連線渲染器
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

  const handleTimeChange = useCallback((e) => {
    setCurrentTimeIndex(parseInt(e.target.value, 10));
  }, []);

  const currentTimeNs = simulationData.time_steps ? simulationData.time_steps[currentTimeIndex] : 0;
  const maxSteps = simulationData.time_steps ? simulationData.time_steps.length - 1 : 0;

  // ===== 時脈步進按鈕 =====
  const stepTime = useCallback((delta) => {
    setCurrentTimeIndex(prev => {
      const next = prev + delta;
      return Math.max(0, Math.min(next, maxSteps));
    });
  }, [maxSteps]);

  // 自訂跳轉
  const [jumpInput, setJumpInput] = useState('');
  const handleJump = useCallback(() => {
    const idx = parseInt(jumpInput, 10);
    if (!isNaN(idx) && idx >= 0 && idx <= maxSteps) {
      setCurrentTimeIndex(idx);
    }
  }, [jumpInput, maxSteps]);

  // ==================== 統計資訊 ====================
  
  const stats = useMemo(() => {
    const expandedCount = Object.keys(expandedGroups).length;
    const totalNodes = nodes.length;
    const groupCount = nodes.filter(n => n.type === 'groupNode').length;
    const variableCount = nodes.filter(n => n.type === 'customNode').length;
    
    return {
      expandedCount,
      totalNodes,
      groupCount,
      variableCount
    };
  }, [expandedGroups, nodes]);

  // ==================== 渲染 UI ====================
  
  return (
    <div style={{ width: '100%', height: '100vh', background: '#0d1117', display: 'flex', flexDirection: 'column' }}>
      {(isGenerating || isPipelineRunning) && (
        <LoadingOverlay>
          <LoadingSpinner />
          <LoadingText>
            {isGenerating ? '正在生成測資中...' : '正在執行硬體分析流水線...'}
          </LoadingText>
        </LoadingOverlay>
      )}

      <StimulusButton onClick={handleOpenStimulusModal} disabled={!bridge || isGenerating || isPipelineRunning}>
        {isGenerating ? '生成中...' : '測資與時脈設定'}
      </StimulusButton>
      
      <LoadVerilogButton onClick={handleLoadVerilogProject} disabled={!bridge || isGenerating || isPipelineRunning}>
        {isPipelineRunning ? '載入中...' : '載入 Verilog 專案'}
      </LoadVerilogButton>

      <InfoPanel>
        <div style={{ marginBottom: '8px', color: '#667eea', fontWeight: '700' }}>
          系統資訊 (Group Nodes 模式)
        </div>
        <div>已展開 Group: {stats.expandedCount}</div>
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

      {isStimulusModalOpen && (
        <StimulusConfigModal
          isOpen={isStimulusModalOpen}
          onClose={handleCloseStimulusModal}
          hierarchyData={graphData}
          onGenerate={handleGenerateStimulus}
        />
      )}

      <div style={{
        background: '#252525',
        padding: '14px 50px 18px',
        borderTop: '1px solid #444',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center'
      }}>
        {/* 第一行：時間資訊 + 步進按鈕 + 跳轉 */}
        <div style={{ 
          color: '#fff', marginBottom: '8px', fontFamily: 'monospace', 
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px', flexWrap: 'wrap'
        }}>
          <strong>模擬時間: {currentTimeNs} ns</strong>
          <span style={{ color: '#888' }}>步進: {currentTimeIndex}/{maxSteps}</span>
          <span style={{ color: '#667eea' }}>頂層模組: {topModule || '...'}</span>

          {/* 步進按鈕群組 */}
          <span style={{ display: 'inline-flex', gap: '4px', marginLeft: '16px' }}>
            {[
              { label: '−10', delta: -10 },
              { label: '−5',  delta: -5  },
              { label: '−1',  delta: -1  },
              { label: '+1',  delta: 1   },
              { label: '+5',  delta: 5   },
              { label: '+10', delta: 10  },
            ].map(({ label, delta }) => (
              <button
                key={label}
                onClick={() => stepTime(delta)}
                disabled={
                  (delta < 0 && currentTimeIndex <= 0) || 
                  (delta > 0 && currentTimeIndex >= maxSteps)
                }
                style={{
                  padding: '3px 8px', fontSize: '12px', fontFamily: 'monospace',
                  background: '#333', color: '#ccc', border: '1px solid #555',
                  borderRadius: '4px', cursor: 'pointer',
                  opacity: ((delta < 0 && currentTimeIndex <= 0) || (delta > 0 && currentTimeIndex >= maxSteps)) ? 0.4 : 1
                }}
              >
                {label}
              </button>
            ))}
          </span>

          {/* 跳轉欄位 */}
          <span style={{ display: 'inline-flex', gap: '4px', marginLeft: '8px', alignItems: 'center' }}>
            <input
              type="number"
              min="0"
              max={maxSteps}
              value={jumpInput}
              onChange={e => setJumpInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleJump(); }}
              placeholder="步進#"
              style={{
                width: '72px', padding: '3px 6px', fontSize: '12px', fontFamily: 'monospace',
                background: '#1a1a1a', color: '#fff', border: '1px solid #555', borderRadius: '4px'
              }}
            />
            <button
              onClick={handleJump}
              style={{
                padding: '3px 10px', fontSize: '12px', fontFamily: 'monospace',
                background: '#667eea', color: '#fff', border: 'none',
                borderRadius: '4px', cursor: 'pointer'
              }}
            >
              跳轉
            </button>
          </span>
        </div>

        {/* 第二行：滑桿 */}
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
