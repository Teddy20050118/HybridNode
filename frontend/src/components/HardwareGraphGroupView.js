/**
 * 硬體階層視圖 - Group 節點橫向遞迴展開架構
 * 
 * 核心概念:
 * 1. 初始畫面僅顯示 Root Module 的變數，包覆在一個半透明 Group 節點內
 * 2. 雙擊子模組實例時，不清空畫面，而是在右側動態新增該模組的 Group 節點
 * 3. 保留跨層級連線，形成由左至右的拓撲展開
 * 
 * 資料結構範例:
 * expandedModules = {
 *   'ROOT_ATE': { x: 0, y: 0, nodes: [...], groupId: 'group_0' },
 *   'FIFO_64_inst_f0': { x: 800, y: 0, nodes: [...], groupId: 'group_1', parentId: 'group_0' }
 * }
 */

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import ReactFlow, { 
  Controls, 
  Background, 
  applyNodeChanges,
  applyEdgeChanges 
} from 'reactflow';
import 'reactflow/dist/style.css';
import styled from 'styled-components';

// 引入自定義元件
import HardwareNode from './HardwareNode';
import CustomHardwareEdge from './CustomHardwareEdge';
import { useBridge } from '../hooks/useBridge';

// 引入佈局工具
import { getLayoutedElements, detectTopModule, buildInstanceToModuleMap } from '../utils/layoutUtils';

// 引入資料
import graphData from '../data/reactflow_data.json';
import simulationData from '../data/simulation_data.json';

// ==================== 樣式組件 ====================

const ModuleGroupContainer = styled.div`
  background: rgba(50, 50, 70, 0.15);
  border: 2px solid rgba(102, 126, 234, 0.4);
  border-radius: 12px;
  padding: 40px 20px 20px 20px;
  position: relative;
  min-width: 600px;
  min-height: 400px;
`;

const ModuleGroupTitle = styled.div`
  position: absolute;
  top: 8px;
  left: 12px;
  font-size: 14px;
  font-weight: bold;
  color: #667eea;
  font-family: 'Consolas', monospace;
  background: rgba(0, 0, 0, 0.6);
  padding: 4px 12px;
  border-radius: 6px;
`;

const CollapseButton = styled.button`
  position: absolute;
  top: 8px;
  right: 12px;
  background: rgba(200, 60, 60, 0.8);
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  font-family: 'Consolas', monospace;
  
  &:hover {
    background: rgba(200, 60, 60, 1);
  }
`;

// ==================== 主元件 ====================

const HardwareGraphGroupView = () => {
  const { bridge } = useBridge();

  // 註冊自定義節點與連線類型
  const nodeTypes = useMemo(() => ({ 
    customNode: HardwareNode,
    groupNode: ModuleGroupNode
  }), []);
  
  const edgeTypes = useMemo(() => ({ 
    hardwareEdge: CustomHardwareEdge 
  }), []);

  // 原始資料
  const [rawNodes] = useState(graphData.reactflow_nodes || []);
  const [rawEdges] = useState(graphData.reactflow_edges || []);
  
  // 時間軸控制
  const [currentTimeIndex, setCurrentTimeIndex] = useState(0);

  // ==================== Group 節點展開狀態管理 ====================
  
  // 已展開的模組集合
  // key: 模組識別碼 (例如: 'ROOT_ATE', 'FIFO_64_inst_f0')
  // value: { x, y, nodes, edges, groupId, parentGroupId }
  const [expandedModules, setExpandedModules] = useState({});
  
  // 實例映射表
  const [instanceToModuleMap, setInstanceToModuleMap] = useState({});
  
  // 顯示的所有節點（包含所有 Group 及其內部節點）
  const [displayedNodes, setDisplayedNodes] = useState([]);
  const [displayedEdges, setDisplayedEdges] = useState([]);

  // 初始化：建立頂層模組的 Group
  useEffect(() => {
    if (Object.keys(expandedModules).length === 0 && rawNodes.length > 0) {
      const topModule = detectTopModule(rawNodes);
      const instanceMap = buildInstanceToModuleMap(rawNodes);
      
      console.log('[GroupView] 初始化頂層模組:', topModule);
      console.log('[GroupView] 實例映射表:', instanceMap);
      
      setInstanceToModuleMap(instanceMap);
      
      // 建立頂層模組的 Group
      expandModule('ROOT', topModule, null, 0, 0);
    }
  }, [rawNodes]);

  // ==================== 模組展開核心邏輯 ====================

  /**
   * 展開模組 - 建立新的 Group 節點
   * 
   * @param {string} instanceName - 實例名稱 (例如: 'f0', 'ROOT')
   * @param {string} moduleName - 模組定義名稱 (例如: 'FIFO_64', 'ATE')
   * @param {string} parentGroupId - 父 Group ID
   * @param {number} baseX - 基準 X 座標
   * @param {number} baseY - 基準 Y 座標
   */
  const expandModule = useCallback((instanceName, moduleName, parentGroupId, baseX, baseY) => {
    const moduleKey = `${moduleName}_inst_${instanceName}`;
    
    // 避免重複展開
    if (expandedModules[moduleKey]) {
      console.warn(`[GroupView] 模組 ${moduleKey} 已展開，跳過`);
      return;
    }

    // 過濾屬於此模組的節點
    const moduleNodes = rawNodes.filter(node => node.data?.module === moduleName);
    
    if (moduleNodes.length === 0) {
      console.warn(`[GroupView] 模組 ${moduleName} 無節點`);
      return;
    }

    // 過濾模組內部連線
    const moduleNodeIds = new Set(moduleNodes.map(n => n.id));
    const moduleEdges = rawEdges.filter(e => 
      moduleNodeIds.has(e.source) && moduleNodeIds.has(e.target)
    );

    // 使用 Dagre 計算佈局
    const layoutedNodes = getLayoutedElements(moduleNodes, moduleEdges, {
      direction: 'LR',
      ranksep: 100,
      nodesep: 60
    });

    // 偏移所有節點座標（相對於 Group 內部）
    const offsetNodes = layoutedNodes.map(node => ({
      ...node,
      position: {
        x: node.position.x + 20,  // Group 內部 padding
        y: node.position.y + 60   // 標題高度
      },
      parentNode: `group_${moduleKey}`,  // 設定父節點為 Group
      extent: 'parent'  // 限制在父節點範圍內
    }));

    // 建立 Group 節點資料
    const newExpandedModule = {
      x: baseX,
      y: baseY,
      nodes: offsetNodes,
      edges: moduleEdges,
      groupId: `group_${moduleKey}`,
      parentGroupId: parentGroupId,
      moduleName: moduleName,
      instanceName: instanceName
    };

    // 更新展開模組集合
    setExpandedModules(prev => ({
      ...prev,
      [moduleKey]: newExpandedModule
    }));

    console.log(`[GroupView] 展開模組: ${moduleKey}, 節點數: ${offsetNodes.length}`);

  }, [rawNodes, rawEdges, expandedModules]);

  /**
   * 收合模組 - 移除 Group 節點及其子樹
   * 
   * @param {string} moduleKey - 模組識別碼
   */
  const collapseModule = useCallback((moduleKey) => {
    setExpandedModules(prev => {
      const newExpanded = { ...prev };
      
      // 遞迴移除此模組及所有子模組
      const removeModuleAndChildren = (key) => {
        const module = newExpanded[key];
        if (!module) return;
        
        // 找出所有以此模組為父的子模組
        Object.keys(newExpanded).forEach(childKey => {
          if (newExpanded[childKey].parentGroupId === module.groupId) {
            removeModuleAndChildren(childKey);
          }
        });
        
        // 移除此模組
        delete newExpanded[key];
        console.log(`[GroupView] 收合模組: ${key}`);
      };
      
      removeModuleAndChildren(moduleKey);
      
      return newExpanded;
    });
  }, []);

  // ==================== 雙擊展開處理 ====================

  /**
   * 處理節點雙擊事件 - 橫向展開子模組
   */
  const handleNodeDoubleClick = useCallback((event, node) => {
    if (node.data?.type !== 'submodule') {
      console.log(`[GroupView] 節點 ${node.id} 類型為 ${node.data?.type}，不可展開`);
      return;
    }

    const instanceName = node.data.label || node.id;
    const targetModuleName = instanceToModuleMap[instanceName];
    
    if (!targetModuleName) {
      console.warn(`[GroupView] 未找到實例 ${instanceName} 的模組映射`);
      return;
    }

    // 計算新 Group 的座標（原節點右側 800px）
    const parentGroup = Object.values(expandedModules).find(m => 
      m.nodes.some(n => n.id === node.id)
    );
    
    if (!parentGroup) {
      console.error(`[GroupView] 找不到節點 ${node.id} 的父 Group`);
      return;
    }

    // 新 Group 放置在父 Group 右側
    const newX = parentGroup.x + 800;
    const newY = parentGroup.y;

    console.log(`[GroupView] 準備展開子模組: ${instanceName} -> ${targetModuleName}`);
    console.log(`[GroupView] 新位置: (${newX}, ${newY})`);

    expandModule(instanceName, targetModuleName, parentGroup.groupId, newX, newY);

  }, [instanceToModuleMap, expandedModules, expandModule]);

  // ==================== 動態建構 React Flow 節點與連線 ====================

  useEffect(() => {
    const allNodes = [];
    const allEdges = [];
    const groupIds = new Set();

    // 步驟 1: 建立所有 Group 節點
    Object.entries(expandedModules).forEach(([moduleKey, moduleData]) => {
      const { x, y, groupId, moduleName, instanceName, nodes } = moduleData;

      // 計算 Group 的尺寸（根據內部節點範圍）
      const nodesBounds = calculateBounds(nodes);
      const groupWidth = Math.max(nodesBounds.width + 40, 600);
      const groupHeight = Math.max(nodesBounds.height + 80, 400);

      // 建立 Group 節點
      const groupNode = {
        id: groupId,
        type: 'groupNode',
        position: { x, y },
        style: {
          width: groupWidth,
          height: groupHeight,
          zIndex: -1  // Group 在最底層
        },
        data: {
          label: `${moduleName} (${instanceName})`,
          moduleKey: moduleKey,
          onCollapse: () => collapseModule(moduleKey)
        }
      };

      allNodes.push(groupNode);
      groupIds.add(groupId);

      // 加入 Group 內部的節點
      allNodes.push(...nodes);

      // 加入 Group 內部的連線
      allEdges.push(...moduleData.edges.map(edge => ({
        ...edge,
        type: 'hardwareEdge'  // 使用自定義連線
      })));
    });

    // 步驟 2: 加入跨 Group 的連線（實例化連線）
    // 找出所有子模組實例節點，建立與展開 Group 內部節點的連線
    Object.values(expandedModules).forEach(moduleData => {
      moduleData.nodes.forEach(node => {
        if (node.data?.type === 'submodule') {
          const instanceName = node.data.label || node.id;
          const childModuleKey = Object.keys(expandedModules).find(key => 
            key.includes(`inst_${instanceName}`)
          );

          if (childModuleKey) {
            const childModule = expandedModules[childModuleKey];
            
            // 建立從父模組實例節點到子模組 Group 的視覺連線
            // (實際連線邏輯需根據 port mapping 分析)
            // 此處為示意性連線
          }
        }
      });
    });

    setDisplayedNodes(allNodes);
    setDisplayedEdges(allEdges);

    console.log(`[GroupView] 更新顯示: ${allNodes.length} 節點, ${allEdges.length} 連線`);

  }, [expandedModules, collapseModule]);

  // ==================== 渲染 ====================

  const onNodesChange = useCallback(
    (changes) => setDisplayedNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );

  const onEdgesChange = useCallback(
    (changes) => setDisplayedEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#0d1117' }}>
      <ReactFlow
        nodes={displayedNodes}
        edges={displayedEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDoubleClick={handleNodeDoubleClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        minZoom={0.1}
        maxZoom={2}
      >
        <Background color="#1f2937" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
};

// ==================== Group 節點組件 ====================

const ModuleGroupNode = ({ data }) => {
  return (
    <ModuleGroupContainer>
      <ModuleGroupTitle>{data.label}</ModuleGroupTitle>
      <CollapseButton onClick={data.onCollapse}>
        收合模組
      </CollapseButton>
    </ModuleGroupContainer>
  );
};

// ==================== 工具函式 ====================

/**
 * 計算節點群組的邊界範圍
 * 
 * @param {Array} nodes - 節點陣列
 * @returns {Object} { width, height, minX, minY, maxX, maxY }
 */
function calculateBounds(nodes) {
  if (nodes.length === 0) {
    return { width: 0, height: 0, minX: 0, minY: 0, maxX: 0, maxY: 0 };
  }

  let minX = Infinity, minY = Infinity;
  let maxX = -Infinity, maxY = -Infinity;

  nodes.forEach(node => {
    const x = node.position.x;
    const y = node.position.y;
    const nodeWidth = 180;  // 預估節點寬度
    const nodeHeight = 90;  // 預估節點高度

    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + nodeWidth);
    maxY = Math.max(maxY, y + nodeHeight);
  });

  return {
    width: maxX - minX,
    height: maxY - minY,
    minX,
    minY,
    maxX,
    maxY
  };
}

export default HardwareGraphGroupView;
