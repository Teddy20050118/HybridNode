/**
 * Header - 頂部導航欄
 * 
 * 包含搜尋框、過濾器、重載按鈕和基本統計信息
 */

import React from 'react';
import styled from 'styled-components';

/**
 * 根本問題修復說明：
 * App.js 的 LoadingOverlay 使用 position:fixed + z-index:9999，
 * 在連線或載入期間會完全覆蓋整個畫面（包含 Header），
 * 導致 Header 內所有元素（包括 Min Risk 滑桿）的 pointer events 都被 overlay 攔截。
 * 解法：將 HeaderContainer 提升至 position:relative + z-index:10000，
 * 確保 Header 永遠渲染在 overlay 之上，滑鼠事件不再被攔截。
 */
const HeaderContainer = styled.header`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  gap: 20px;
  flex-wrap: wrap;
  /* 使 Header 永遠覆蓋在 LoadingOverlay（z-index:9999）之上 */
  position: relative;
  z-index: 10000;
`;

const Logo = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 20px;
  font-weight: 700;
  color: #c9d1d9;
  white-space: nowrap;
`;

const SearchContainer = styled.div`
  flex: 1;
  max-width: 500px;
  min-width: 200px;
`;

const SearchInput = styled.input`
  width: 100%;
  padding: 8px 16px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  font-size: 14px;
  transition: all 0.2s;
  
  &:focus {
    outline: none;
    border-color: #388bfd;
    box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.1);
  }
  
  &::placeholder {
    color: #8b949e;
  }
`;

const Controls = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
`;

const FilterGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const FilterLabel = styled.label`
  color: #8b949e;
  font-size: 13px;
  white-space: nowrap;
`;

const FilterSlider = styled.input`
  width: 120px;
  accent-color: #388bfd;
  /* 明確設定 cursor，避免部分瀏覽器/WebView 繼承 not-allowed */
  cursor: pointer;
  &:disabled {
    cursor: not-allowed;
    opacity: 0.4;
  }
`;

const FilterValue = styled.span`
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 600;
  min-width: 30px;
  text-align: right;
`;

const Button = styled.button`
  padding: 8px 16px;
  background: ${props => props.primary ? '#238636' : '#21262d'};
  color: #c9d1d9;
  border: 1px solid ${props => props.primary ? '#238636' : '#30363d'};
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  
  &:hover {
    background: ${props => props.primary ? '#2ea043' : '#30363d'};
  }
  
  &:active {
    transform: scale(0.98);
  }
`;

const StatsBar = styled.div`
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 10px;
  border-left: 1px solid #30363d;
  margin-left: 10px;
`;

const StatItem = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
`;

const StatValue = styled.div`
  color: ${props => props.color || '#c9d1d9'};
  font-size: 18px;
  font-weight: 700;
`;

const StatLabel = styled.div`
  color: #8b949e;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const Header = ({
  searchQuery,
  onSearch,
  filterMinRisk,
  onFilterChange,
  showAllNodes,
  onToggleShowAll,
  onReload,
  onOpenProject,
  stats
}) => {
  return (
    <HeaderContainer>
      {/* Logo */}
      <Logo>
        HybridNode
      </Logo>

      {/* 搜尋框 */}
      <SearchContainer>
        <SearchInput
          type="text"
          placeholder="Search nodes by name or ID..."
          value={searchQuery}
          onChange={(e) => onSearch(e.target.value)}
        />
      </SearchContainer>

      {/* 控制器 */}
      <Controls>
        {/* 風險過濾器 */}
        <FilterGroup>
          <FilterLabel>Min Risk:</FilterLabel>
          <FilterSlider
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={filterMinRisk}
            disabled={showAllNodes}
            onChange={(e) => onFilterChange(parseFloat(e.target.value))}
          />
          <FilterValue>{(filterMinRisk * 100).toFixed(0)}%</FilterValue>
        </FilterGroup>

        {/* 顯示所有節點切換開關 */}
        <Button
          onClick={onToggleShowAll}
          style={{
            background: showAllNodes ? '#1f6feb' : '#21262d',
            borderColor: showAllNodes ? '#1f6feb' : '#30363d',
            fontSize: '13px',
            padding: '6px 12px',
          }}
        >
          {showAllNodes ? '[ALL] 顯示全部節點' : '[FILTER] 規則過濾中'}
        </Button>

        {/* 開啟專案按鈕 */}
        {onOpenProject && (
          <Button onClick={onOpenProject} primary>
            Open Project
          </Button>
        )}

        {/* 重載按鈕 */}
        <Button onClick={onReload}>
          Reload
        </Button>
      </Controls>

      {/* 統計欄 */}
      {stats && (
        <StatsBar>
          <StatItem>
            <StatValue>{stats.total_nodes}</StatValue>
            <StatLabel>Nodes</StatLabel>
          </StatItem>
          <StatItem>
            <StatValue color={stats.risky_nodes > 0 ? '#f85149' : '#2ea043'}>
              {stats.risky_nodes}
            </StatValue>
            <StatLabel>Risks</StatLabel>
          </StatItem>
          <StatItem>
            <StatValue color={stats.risk_percentage >= 20 ? '#f85149' : stats.risk_percentage >= 10 ? '#f0e130' : '#2ea043'}>
              {stats.risk_percentage.toFixed(1)}%
            </StatValue>
            <StatLabel>Risk %</StatLabel>
          </StatItem>
        </StatsBar>
      )}
    </HeaderContainer>
  );
};

export default Header;
