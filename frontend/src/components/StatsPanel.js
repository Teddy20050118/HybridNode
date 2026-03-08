/**
 * StatsPanel - 左側統計面板
 * 
 * 顯示圖的詳細統計信息
 */

import React from 'react';
import styled from 'styled-components';

const PanelContainer = styled.div`
  width: 280px;
  background: #161b22;
  border-right: 1px solid #30363d;
  padding: 20px;
  overflow-y: auto;
  
  /* 捲軸樣式 */
  &::-webkit-scrollbar {
    width: 8px;
  }
  
  &::-webkit-scrollbar-track {
    background: #0d1117;
  }
  
  &::-webkit-scrollbar-thumb {
    background: #30363d;
    border-radius: 4px;
  }
`;

const PanelTitle = styled.h3`
  margin: 0 0 20px 0;
  color: #c9d1d9;
  font-size: 16px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const StatSection = styled.div`
  margin-bottom: 24px;
`;

const SectionTitle = styled.h4`
  margin: 0 0 12px 0;
  color: #58a6ff;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const StatItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: #0d1117;
  border-radius: 6px;
  border-left: 3px solid ${props => props.color || '#30363d'};
`;

const StatLabel = styled.span`
  color: #8b949e;
  font-size: 13px;
`;

const StatValue = styled.span`
  color: ${props => props.color || '#c9d1d9'};
  font-size: 16px;
  font-weight: 700;
`;

const ProgressBar = styled.div`
  width: 100%;
  height: 8px;
  background: #0d1117;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 8px;
`;

const ProgressFill = styled.div`
  height: 100%;
  width: ${props => props.percentage}%;
  background: ${props => props.color || '#388bfd'};
  transition: width 0.3s ease;
`;

const Divider = styled.div`
  height: 1px;
  background: #30363d;
  margin: 20px 0;
`;

const Legend = styled.div`
  margin-top: 12px;
`;

const LegendItem = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #8b949e;
`;

const LegendColor = styled.div`
  width: 16px;
  height: 16px;
  border-radius: ${props => props.shape === 'square' ? '3px' : '50%'};
  background: ${props => props.color};
`;

const StatsPanel = ({ stats }) => {
  if (!stats) {
    return (
      <PanelContainer>
        <PanelTitle>Statistics</PanelTitle>
        <StatItem>
          <StatLabel>Loading...</StatLabel>
        </StatItem>
      </PanelContainer>
    );
  }

  const riskColor = stats.risk_percentage >= 20 ? '#f85149' : stats.risk_percentage >= 10 ? '#f0e130' : '#2ea043';

  return (
    <PanelContainer>
      <PanelTitle>Statistics</PanelTitle>

      {/* 圖結構統計 */}
      <StatSection>
        <SectionTitle>Graph Structure</SectionTitle>
        <StatItem color="#388bfd">
          <StatLabel>Total Nodes</StatLabel>
          <StatValue>{stats.total_nodes}</StatValue>
        </StatItem>
        <StatItem color="#8b949e">
          <StatLabel>Total Links</StatLabel>
          <StatValue>{stats.total_links}</StatValue>
        </StatItem>
        <StatItem color="#8b949e">
          <StatLabel>Isolated Nodes</StatLabel>
          <StatValue>{stats.isolated_nodes}</StatValue>
        </StatItem>
      </StatSection>

      <Divider />

      {/* 風險統計 */}
      <StatSection>
        <SectionTitle>Risk Analysis</SectionTitle>
        <StatItem color={riskColor}>
          <StatLabel>Risky Nodes</StatLabel>
          <StatValue color={riskColor}>{stats.risky_nodes}</StatValue>
        </StatItem>
        <StatItem color={riskColor}>
          <StatLabel>Risk Percentage</StatLabel>
          <StatValue color={riskColor}>{stats.risk_percentage.toFixed(1)}%</StatValue>
        </StatItem>
        <ProgressBar>
          <ProgressFill percentage={stats.risk_percentage} color={riskColor} />
        </ProgressBar>
      </StatSection>

      <Divider />

      {/* 代碼質量統計 */}
      <StatSection>
        <SectionTitle>Code Quality</SectionTitle>
        <StatItem color="#a371f7">
          <StatLabel>Total LOC</StatLabel>
          <StatValue>{stats.total_loc.toLocaleString()}</StatValue>
        </StatItem>
        <StatItem color="#a371f7">
          <StatLabel>Avg LOC/Node</StatLabel>
          <StatValue>{stats.avg_loc.toFixed(1)}</StatValue>
        </StatItem>
        <StatItem color="#a371f7">
          <StatLabel>Avg Complexity</StatLabel>
          <StatValue>{stats.avg_complexity.toFixed(1)}</StatValue>
        </StatItem>
      </StatSection>

      <Divider />

      {/* 圖例 */}
      <StatSection>
        <SectionTitle>Legend</SectionTitle>
        <Legend>
          <LegendItem>
            <LegendColor color="#f85149" />
            High Risk (70-100%)
          </LegendItem>
          <LegendItem>
            <LegendColor color="#f0e130" />
            Medium Risk (40-70%)
          </LegendItem>
          <LegendItem>
            <LegendColor color="#2ea043" />
            Low Risk (0-40%)
          </LegendItem>
        </Legend>
        
        <Legend style={{ marginTop: '16px' }}>
          <LegendItem>
            <LegendColor color="#388bfd" shape="circle" />
            Function
          </LegendItem>
          <LegendItem>
            <LegendColor color="#388bfd" shape="square" />
            Class / Struct
          </LegendItem>
        </Legend>
      </StatSection>
    </PanelContainer>
  );
};

export default StatsPanel;
