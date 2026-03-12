import React, { useState, useEffect } from 'react';
import styled from 'styled-components';

// --- Styled Components (確保沒有 Emoji，且符合深色主題) ---
const ModalOverlay = styled.div`
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 99999;
  font-family: 'Consolas', monospace;
`;

const ModalContainer = styled.div`
  background: #1e1e1e;
  border: 1px solid #333;
  border-radius: 8px;
  width: 700px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
  color: #e0e0e0;
`;

const Header = styled.div`
  padding: 20px;
  border-bottom: 1px solid #333;
  background: #252525;
  border-radius: 8px 8px 0 0;
`;

const Title = styled.h2`
  margin: 0;
  color: #fff;
  font-size: 20px;
`;

const Subtitle = styled.div`
  color: #888;
  font-size: 14px;
  margin-top: 5px;
`;

const Content = styled.div`
  padding: 20px;
`;

const SectionTitle = styled.h3`
  font-size: 16px;
  color: #66ccff;
  border-bottom: 1px solid #333;
  padding-bottom: 5px;
  margin-top: 25px;
  margin-bottom: 15px;
`;

const InputRow = styled.div`
  display: flex;
  align-items: center;
  margin-bottom: 15px;
  background: #2a2a2a;
  padding: 10px;
  border-radius: 4px;
`;

const Label = styled.div`
  width: 120px;
  font-weight: bold;
  color: #ccc;
`;

const StyledInput = styled.input`
  background: #111;
  border: 1px solid #444;
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  flex: 1;
  margin-right: 10px;
  font-family: inherit;
  &:focus { outline: none; border-color: #66ccff; }
`;

const StyledSelect = styled.select`
  background: #111;
  border: 1px solid #444;
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  width: 100px;
  font-family: inherit;
  &:focus { outline: none; border-color: #66ccff; }
`;

const ButtonContainer = styled.div`
  padding: 20px;
  border-top: 1px solid #333;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  background: #252525;
  border-radius: 0 0 8px 8px;
`;

const Button = styled.button`
  background: ${props => props.primary ? '#1f6feb' : '#333'};
  color: white;
  border: 1px solid ${props => props.primary ? '#1f6feb' : '#555'};
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
  transition: all 0.2s;
  
  &:hover {
    background: ${props => props.primary ? '#388bfd' : '#444'};
  }
`;

// --- Main Component ---
const StimulusConfigModal = ({ isOpen, onClose, hierarchyData, onGenerate }) => {
  // 表單狀態
  const [topModule, setTopModule] = useState('');
  const [clockConfig, setClockConfig] = useState({ signal_name: 'clk', period_ns: 10 });
  const [resetConfig, setResetConfig] = useState({ signal_name: 'reset', active_high: true, duration_ns: 20 });
  const [bindings, setBindings] = useState([]);
  const [outputs, setOutputs] = useState([]);
  const [simCycles, setSimCycles] = useState(4096);

  // 初始化資料（當 hierarchyData 傳入時解析）
  useEffect(() => {
    if (!isOpen || !hierarchyData || !hierarchyData.hierarchy) return;

    const top = hierarchyData.hierarchy.top_module;
    setTopModule(top);

    const ports = hierarchyData.module_ports[top];
    if (ports) {
      // 處理 Inputs
      const initialBindings = ports.inputs
        .filter(inp => inp.name !== 'clk' && inp.name !== 'reset') // 排除預設的 clk/reset
        .map(inp => ({
          input_name: inp.name,
          width: inp.width,
          data_file: `${inp.name}_data.dat`, // 預設檔名
          radix: inp.width > 1 ? 'hex' : 'bin',
          description: `${inp.width}-bit 輸入`
        }));
      setBindings(initialBindings);
      
      // 處理 Outputs
      setOutputs(ports.outputs.map(out => ({
        name: out.name,
        width: out.width,
        description: `${out.width}-bit 輸出`
      })));
    }
  }, [isOpen, hierarchyData]);

  if (!isOpen) return null;

  // 處理綁定資料更新
  const handleBindingChange = (index, field, value) => {
    const newBindings = [...bindings];
    newBindings[index][field] = value;
    setBindings(newBindings);
  };

  // 提交生成
  const handleSubmit = () => {
    const configData = {
      top_module: topModule,
      clock: { ...clockConfig, initial_value: 0 },
      reset: resetConfig,
      stimulus_bindings: bindings,
      outputs: outputs,
      simulation: {
        test_cycles: parseInt(simCycles),
        vcd_output: `${topModule}_auto_sim.vcd`,
        display_interval: 512
      },
      comments: {
        purpose: "Auto-generated Testbench Config from UI",
        date: new Date().toISOString().split('T')[0]
      }
    };
    onGenerate(configData);
  };

  return (
    <ModalOverlay>
      <ModalContainer>
        <Header>
          <Title>測資自動綁定設定 (Stimulus Config)</Title>
          <Subtitle>頂層模組: {topModule || '未知'}</Subtitle>
        </Header>
        
        <Content>
          <SectionTitle>時脈與重置 (Clock & Reset)</SectionTitle>
          <InputRow>
            <Label>Clock 週期 (ns)</Label>
            <StyledInput 
              type="number" 
              value={clockConfig.period_ns} 
              onChange={e => setClockConfig({...clockConfig, period_ns: parseInt(e.target.value)})} 
            />
          </InputRow>
          <InputRow>
            <Label>Reset 維持 (ns)</Label>
            <StyledInput 
              type="number" 
              value={resetConfig.duration_ns} 
              onChange={e => setResetConfig({...resetConfig, duration_ns: parseInt(e.target.value)})} 
            />
            <Label style={{ width: 'auto', marginLeft: '10px', marginRight: '5px' }}>Active High:</Label>
            <input 
              type="checkbox" 
              checked={resetConfig.active_high}
              onChange={e => setResetConfig({...resetConfig, active_high: e.target.checked})}
            />
          </InputRow>

          <SectionTitle>輸入腳位測資綁定 (Stimulus Bindings)</SectionTitle>
          {bindings.length === 0 ? (
            <div style={{ color: '#888', fontStyle: 'italic' }}>未偵測到需要綁定測資的輸入腳位。</div>
          ) : (
            bindings.map((binding, index) => (
              <InputRow key={binding.input_name}>
                <Label>{binding.input_name} [{binding.width}-bit]</Label>
                <StyledInput 
                  placeholder="輸入檔名 (如 tb1.map)" 
                  value={binding.data_file}
                  onChange={e => handleBindingChange(index, 'data_file', e.target.value)}
                />
                <StyledSelect 
                  value={binding.radix}
                  onChange={e => handleBindingChange(index, 'radix', e.target.value)}
                >
                  <option value="bin">二進位 (bin)</option>
                  <option value="hex">十六進位 (hex)</option>
                  <option value="dec">十進位 (dec)</option>
                </StyledSelect>
              </InputRow>
            ))
          )}

          <SectionTitle>模擬設定 (Simulation Control)</SectionTitle>
          <InputRow>
            <Label>總模擬週期數</Label>
            <StyledInput 
              type="number" 
              value={simCycles} 
              onChange={e => setSimCycles(e.target.value)} 
            />
          </InputRow>
        </Content>

        <ButtonContainer>
          <Button onClick={onClose}>取消 (Cancel)</Button>
          <Button primary onClick={handleSubmit}>產生 TB 並模擬 (Generate & Simulate)</Button>
        </ButtonContainer>
      </ModalContainer>
    </ModalOverlay>
  );
};

export default StimulusConfigModal;