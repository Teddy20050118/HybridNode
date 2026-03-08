/**
 * Sidebar - 節點詳細信息側邊欄
 * 
 * 顯示選中節點的完整特徵、風險原因、鄰居節點等信息
 */

import React from 'react';
import styled from 'styled-components';

const SidebarContainer = styled.div`
  width: ${props => props.isOpen ? '400px' : '0'};
  height: 100%;
  background: #161b22;
  border-left: 1px solid #30363d;
  transition: width 0.3s ease;
  overflow-y: auto;
  overflow-x: hidden;
  box-shadow: ${props => props.isOpen ? '-2px 0 8px rgba(0, 0, 0, 0.3)' : 'none'};
  
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
  
  &::-webkit-scrollbar-thumb:hover {
    background: #484f58;
  }
`;

const SidebarContent = styled.div`
  padding: 20px;
  display: ${props => props.isOpen ? 'block' : 'none'};
`;

const CloseButton = styled.button`
  position: absolute;
  top: 10px;
  right: 10px;
  background: transparent;
  border: none;
  color: #8b949e;
  font-size: 24px;
  cursor: pointer;
  padding: 5px 10px;
  border-radius: 6px;
  transition: all 0.2s;
  
  &:hover {
    background: #21262d;
    color: #c9d1d9;
  }
`;

const NodeTitle = styled.h2`
  margin: 0 0 10px 0;
  color: #c9d1d9;
  font-size: 20px;
  word-break: break-word;
`;

const NodeId = styled.div`
  color: #8b949e;
  font-size: 12px;
  margin-bottom: 20px;
  font-family: monospace;
`;

const Section = styled.div`
  margin-bottom: 25px;
`;

const SectionTitle = styled.h3`
  margin: 0 0 12px 0;
  color: #58a6ff;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const InfoGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
`;

const InfoItem = styled.div`
  background: #0d1117;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #30363d;
`;

const InfoLabel = styled.div`
  color: #8b949e;
  font-size: 11px;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const InfoValue = styled.div`
  color: #c9d1d9;
  font-size: 16px;
  font-weight: 600;
  
  &.risk-high {
    color: #f85149;
  }
  
  &.risk-medium {
    color: #f0e130;
  }
  
  &.risk-low {
    color: #2ea043;
  }
`;

const RiskBadge = styled.span`
  display: inline-block;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  background: ${props => props.risk === 1 ? 'rgba(248, 81, 73, 0.15)' : 'rgba(46, 160, 67, 0.15)'};
  color: ${props => props.risk === 1 ? '#f85149' : '#2ea043'};
  border: 1px solid ${props => props.risk === 1 ? '#f85149' : '#2ea043'};
`;

const RiskReasonsList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 8px 0 0 0;
`;

const RiskReason = styled.li`
  background: rgba(248, 81, 73, 0.1);
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  border-left: 3px solid #f85149;
  font-size: 13px;
  color: #c9d1d9;
`;

const FeatureList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const FeatureItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: #0d1117;
  border-radius: 4px;
  font-size: 12px;
`;

const FeatureName = styled.span`
  color: #8b949e;
`;

const FeatureValue = styled.span`
  color: #c9d1d9;
  font-weight: 600;
  font-family: monospace;
`;

const NeighborList = styled.div`
  max-height: 200px;
  overflow-y: auto;
`;

const NeighborItem = styled.div`
  padding: 8px 12px;
  background: #0d1117;
  border-radius: 6px;
  margin-bottom: 6px;
  border-left: 3px solid ${props => props.type === 'in' ? '#388bfd' : '#8b949e'};
  
  &:hover {
    background: #161b22;
  }
`;

const NeighborName = styled.div`
  color: #c9d1d9;
  font-size: 13px;
  font-weight: 500;
`;

const NeighborType = styled.div`
  color: #8b949e;
  font-size: 11px;
  margin-top: 2px;
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100%;
  color: #8b949e;
  text-align: center;
  padding: 40px 20px;
`;

const EmptyText = styled.div`
  font-size: 14px;
  line-height: 1.6;
`;

const Sidebar = ({ node, onClose }) => {
  const isOpen = node !== null;

  if (!isOpen) {
    return (
      <SidebarContainer isOpen={false}>
        <EmptyState>
          <EmptyText>
            Click on a node to view<br />detailed information
          </EmptyText>
        </EmptyState>
      </SidebarContainer>
    );
  }

  // 獲取風險等級類名
  const getRiskClass = (score) => {
    if (score >= 0.7) return 'risk-high';
    if (score >= 0.4) return 'risk-medium';
    return 'risk-low';
  };

  return (
    <SidebarContainer isOpen={isOpen}>
      <SidebarContent isOpen={isOpen}>
        <CloseButton onClick={onClose}>&times;</CloseButton>

        {/* 節點標題 */}
        <NodeTitle>{node.name}</NodeTitle>
        <NodeId>{node.id}</NodeId>

        {/* 風險評估 */}
        <Section>
          <SectionTitle>Risk Assessment</SectionTitle>
          <InfoGrid>
            <InfoItem>
              <InfoLabel>Risk Score</InfoLabel>
              <InfoValue className={getRiskClass(node.risk_score)}>
                {(node.risk_score * 100).toFixed(0)}%
              </InfoValue>
            </InfoItem>
            <InfoItem>
              <InfoLabel>Status</InfoLabel>
              <div>
                <RiskBadge risk={node.risk_label}>
                  {node.risk_label === 1 ? 'High Risk' : 'Safe'}
                </RiskBadge>
              </div>
            </InfoItem>
          </InfoGrid>

          {/* 風險原因 */}
          {node.risk_reasons && node.risk_reasons.length > 0 && (
            <>
              <InfoLabel style={{ marginTop: '12px', marginBottom: '8px' }}>
                Risk Reasons
              </InfoLabel>
              <RiskReasonsList>
                {node.risk_reasons.map((reason, idx) => (
                  <RiskReason key={idx}>{reason}</RiskReason>
                ))}
              </RiskReasonsList>
            </>
          )}
        </Section>

        {/* 基本信息 */}
        <Section>
          <SectionTitle>Basic Information</SectionTitle>
          <InfoGrid>
            <InfoItem>
              <InfoLabel>Type</InfoLabel>
              <InfoValue>{node.type}</InfoValue>
            </InfoItem>
            <InfoItem>
              <InfoLabel>Lines of Code</InfoLabel>
              <InfoValue>{node.loc}</InfoValue>
            </InfoItem>
            <InfoItem>
              <InfoLabel>Complexity</InfoLabel>
              <InfoValue>{node.complexity}</InfoValue>
            </InfoItem>
            <InfoItem>
              <InfoLabel>Connections</InfoLabel>
              <InfoValue>
                {node.in_degree} in / {node.out_degree} out
              </InfoValue>
            </InfoItem>
          </InfoGrid>
        </Section>

        {/* AI 特徵 */}
        {node.features && Object.keys(node.features).length > 0 && (
          <Section>
            <SectionTitle>AI Features</SectionTitle>
            <FeatureList>
              {Object.entries(node.features)
                .slice(0, 10) // 只顯示前 10 個特徵
                .map(([name, value]) => (
                  <FeatureItem key={name}>
                    <FeatureName>{name}</FeatureName>
                    <FeatureValue>
                      {typeof value === 'number' ? value.toFixed(3) : value}
                    </FeatureValue>
                  </FeatureItem>
                ))}
            </FeatureList>
          </Section>
        )}

        {/* 鄰居節點 - 出度 */}
        {node.neighbors_out && node.neighbors_out.length > 0 && (
          <Section>
            <SectionTitle>Calls To ({node.neighbors_out.length})</SectionTitle>
            <NeighborList>
              {node.neighbors_out.map((neighbor, idx) => (
                <NeighborItem key={idx} type="out">
                  <NeighborName>{neighbor.name}</NeighborName>
                  <NeighborType>{neighbor.dependency}</NeighborType>
                </NeighborItem>
              ))}
            </NeighborList>
          </Section>
        )}

        {/* 鄰居節點 - 入度 */}
        {node.neighbors_in && node.neighbors_in.length > 0 && (
          <Section>
            <SectionTitle>Called By ({node.neighbors_in.length})</SectionTitle>
            <NeighborList>
              {node.neighbors_in.map((neighbor, idx) => (
                <NeighborItem key={idx} type="in">
                  <NeighborName>{neighbor.name}</NeighborName>
                  <NeighborType>{neighbor.dependency}</NeighborType>
                </NeighborItem>
              ))}
            </NeighborList>
          </Section>
        )}
      </SidebarContent>
    </SidebarContainer>
  );
};

export default Sidebar;
